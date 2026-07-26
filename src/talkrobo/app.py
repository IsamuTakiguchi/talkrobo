"""会話ループ本体。

1ターンの流れ:
    発話をきく → (相づち開始) → Claude にストリーミング要求
      → 先頭の感情タグを抜いて からだ に反映
      → 文が確定するたびに voice へ流し込む（全文を待たない）
      → 鳴り終わるまで待って IDLE に戻る
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import anthropic
from rich.console import Console

from .config import Config
from .listen import InputSource
from .llm.client import ChatClient
from .llm.emotion_tag import EmotionTagExtractor
from .llm.memory import History, Profile
from .llm.safety import clean_for_speech
from .llm.sentence_splitter import SentenceSplitter
from .persona import Persona, build_system_prompt
from .states import Emotion, RobotState

log = logging.getLogger(__name__)


class FillerController(Protocol):
    """考え中の相づちを出す係（Phase 2 で実装）。"""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def timed_out(self) -> bool: ...


class TurnRecorder(Protocol):
    """会話ログと使用量の記録係（Phase 4 で実装）。"""

    def record_user(self, text: str) -> None: ...
    def record_robot(self, text: str, emotion: Emotion) -> None: ...
    def record_usage(self, model: str, usage: Any) -> None: ...


class TalkRobo:
    """ロボット1体ぶんの会話セッション。"""

    def __init__(
        self,
        *,
        config: Config,
        persona: Persona,
        profile: Profile,
        client: ChatClient,
        source: InputSource,
        voice: Any,
        body: Any,
        filler: FillerController | None = None,
        recorder: TurnRecorder | None = None,
        wav_cache: dict[str, Path] | None = None,
        console: Console | None = None,
        should_stop: Callable[[], str | None] | None = None,
    ) -> None:
        self.config = config
        self.persona = persona
        self.profile = profile
        self.client = client
        self.source = source
        self.voice = voice
        self.body = body
        self.filler = filler
        self.recorder = recorder
        self.wav_cache = wav_cache or {}
        self.console = console or Console()
        # 会話を打ち切るべきか（時間制限・予算上限）。理由の文字列を返すと終了する
        self.should_stop = should_stop

        self.history = History(max_turns=config.llm.history_turns)
        self.system_prompt = build_system_prompt(
            persona,
            child_name=profile.child.call_name,
            age=profile.child.age,
            facts=profile.facts,
        )

    # ------------------------------------------------------------------
    # 決まり文句（API を呼ばない）
    # ------------------------------------------------------------------
    def say_line(self, key: str, *, emotion: Emotion = Emotion.FUTSUU, **fmt: str) -> str:
        text = self.persona.line(key)
        if not text:
            return ""
        for k, v in fmt.items():
            text = text.replace("{" + k + "}", v)
        self.body.set_emotion(emotion)
        self.body.set_state(RobotState.SPEAKING)
        self._begin_voice_turn()
        self.voice.say(text, cached_wav=self.wav_cache.get(text))
        self.voice.wait_until_idle()
        self.body.set_state(RobotState.IDLE)
        return text

    def _begin_voice_turn(self) -> None:
        begin = getattr(self.voice, "begin_turn", None)
        if callable(begin):
            begin()

    # ------------------------------------------------------------------
    # メインループ
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.body.set_state(RobotState.IDLE)
        self.say_line("greeting", emotion=Emotion.URESHII)

        try:
            while True:
                stop_reason = self.should_stop() if self.should_stop else None
                if stop_reason:
                    self.say_line(stop_reason, emotion=Emotion.NEMUI)
                    break

                self.body.set_state(RobotState.LISTENING)
                text = self.source.listen(on_captured=self._on_captured)

                if text is None:
                    self.say_line("farewell", emotion=Emotion.URESHII)
                    break
                if not text.strip():
                    self._stop_filler()
                    self.say_line("not_heard", emotion=Emotion.KOMATTA)
                    continue

                if self.recorder:
                    self.recorder.record_user(text)
                self.respond(text)
        except KeyboardInterrupt:
            self.console.print()
            self._stop_filler()
            self.say_line("farewell", emotion=Emotion.URESHII)

    def _on_captured(self) -> None:
        """入力を取り終えた瞬間（＝内容が確定する前）に呼ばれる。"""
        self.body.set_state(RobotState.THINKING)
        if self.filler:
            self.filler.start()

    def _stop_filler(self) -> None:
        if self.filler:
            self.filler.stop()

    # ------------------------------------------------------------------
    # 1ターンの返事
    # ------------------------------------------------------------------
    def respond(self, user_text: str) -> str:
        self.history.add_user(user_text)
        self.body.set_state(RobotState.THINKING)

        extractor = EmotionTagExtractor()
        splitter = SentenceSplitter()
        spoken: list[str] = []
        emotion_applied = False
        first_sentence = True

        def emit(sentences: list[str]) -> None:
            nonlocal first_sentence
            for raw in sentences:
                sentence = clean_for_speech(raw)
                if not sentence:
                    continue
                if first_sentence:
                    # 本応答が始まったので相づちは止める
                    self._stop_filler()
                    self._begin_voice_turn()
                    self.body.set_state(RobotState.SPEAKING)
                    first_sentence = False
                self.voice.say(sentence, cached_wav=self.wav_cache.get(sentence))
                spoken.append(sentence)

        try:
            for delta in self.client.stream_reply(self.system_prompt, self.history.messages):
                body_text = extractor.feed(delta)
                if extractor.resolved and not emotion_applied:
                    self.body.set_emotion(extractor.emotion)
                    emotion_applied = True
                if body_text:
                    emit(splitter.feed(body_text))

            tail = extractor.flush()
            if tail:
                emit(splitter.feed(tail))
            emit(splitter.flush())

        except anthropic.APIError:
            log.exception("Claude API の呼び出しに失敗しました")
            self._stop_filler()
            self.say_line("error", emotion=Emotion.KOMATTA)
            return ""

        if not emotion_applied:
            self.body.set_emotion(extractor.emotion)

        # 安全機構による拒否。content を読む前に stop_reason を見るのが鉄則
        if self.client.last.refused and not spoken:
            self._stop_filler()
            text = self.say_line("refusal", emotion=Emotion.KOMATTA)
            self.history.add_assistant(text)
            return text

        self.voice.wait_until_idle()
        self.body.set_state(RobotState.IDLE)

        reply = "".join(spoken)
        if not reply.strip():
            self._stop_filler()
            reply = self.say_line("not_heard", emotion=Emotion.KOMATTA)

        self.history.add_assistant(reply)
        if self.recorder:
            self.recorder.record_robot(reply, extractor.emotion)
            self.recorder.record_usage(
                self.client.last.model or self.client.model, self.client.last.usage
            )
        return reply

    # ------------------------------------------------------------------
    def close(self) -> None:
        self._stop_filler()
        self.voice.close()
        self.source.close()
        self.body.close()
