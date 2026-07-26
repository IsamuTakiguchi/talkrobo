"""初回起動時に、子供に名前をたずねて覚える。

`voice.say()` と `source.listen()` しか使わないので、
テキストモードでも音声モードでも同じコードが動く。

音声認識は子供の名前をよく間違えるため、3段構えで精度を確保する:
  1. STT に「なまえは」というヒントを与えて短い固有名詞を出やすくする
  2. Claude の構造化出力で「春人です」→ {display:"はると", reading:"ハルト"} に正規化
  3. 合成音声で読み上げて本人に確認してもらう（OK が出た読みだけ採用する）
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..persona import Persona
from ..states import Emotion, RobotState
from .client import ChatClient
from .memory import ChildProfile, Profile

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
STT_HINT = "なまえは"

_YES = ("うん", "はい", "そう", "あって", "おっけ", "ok", "いいよ", "せいかい", "だよ")
_NO = ("ちがう", "違う", "ううん", "いいえ", "ちゃう", "やだ", "じゃない")

_NAME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display": {
            "type": "string",
            "description": "呼びかけに使う名前。ひらがなにする。敬称や余分な語は除く",
        },
        "reading": {
            "type": "string",
            "description": "読み方をカタカナで。音声合成にそのまま渡せる形",
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["display", "reading", "confidence"],
    "additionalProperties": False,
}

_NAME_SYSTEM = """\
あなたは音声認識の結果から「子供の名前」だけを取り出す係です。

入力は、子供が名前を聞かれて答えた音声の認識結果です。
認識ミス・敬語・余計な語が混ざっています。

ルール:
- display は必ずひらがなにする（子供向けなので漢字にしない）
- reading は音声合成にそのまま渡せるカタカナにする
- 「です」「だよ」「といいます」「ぼくは」「わたしは」などは取り除く
- 名前らしきものが見つからなければ display と reading を空文字にし、confidence を low にする
- 認識結果が明らかに名前ではない文（「わからない」など）のときも空文字にする

例:
  入力「春人です」        → display "はると", reading "ハルト", confidence high
  入力「ぼくはさくら」    → display "さくら", reading "サクラ", confidence high
  入力「えーっと」        → display "", reading "", confidence low
"""


def _is_yes(text: str) -> bool:
    lowered = text.lower()
    if any(word in lowered for word in _NO):
        return False
    return any(word in lowered for word in _YES)


def _is_no(text: str) -> bool:
    return any(word in text.lower() for word in _NO)


def _set_hint(source: Any, hint: str | None) -> None:
    """音声入力側が対応していればヒントを渡す（テキスト入力では何もしない）。"""
    setter = getattr(source, "set_hint", None)
    if callable(setter):
        setter(hint)


def _normalize_name(client: ChatClient, raw: str) -> tuple[str, str, str]:
    """(display, reading, confidence) を返す。失敗したら生の文字列で代用する。"""
    fallback = raw.strip(), raw.strip(), "low"
    try:
        result = client.complete_json(
            system=_NAME_SYSTEM,
            user=f"音声認識の結果: 「{raw}」",
            schema=_NAME_SCHEMA,
            max_tokens=128,
        )
    except Exception:
        log.exception("名前の正規化に失敗しました")
        return fallback
    if not result:
        return fallback

    display = str(result.get("display", "")).strip()
    reading = str(result.get("reading", "")).strip() or display
    confidence = str(result.get("confidence", "low")).strip()
    if not display:
        return "", "", "low"
    return display, reading, confidence


class _Speaker:
    """ペルソナのセリフを喋らせる小さなヘルパ。"""

    def __init__(self, persona: Persona, voice: Any, body: Any, wav_cache: dict[str, Any]) -> None:
        self._persona = persona
        self._voice = voice
        self._body = body
        self._cache = wav_cache

    def say(self, key: str, *, emotion: Emotion = Emotion.FUTSUU, **fmt: str) -> None:
        template = self._persona.onboarding.get(key, "")
        if not template:
            return
        text = template
        for k, v in fmt.items():
            text = text.replace("{" + k + "}", v)

        self._body.set_emotion(emotion)
        self._body.set_state(RobotState.SPEAKING)
        begin = getattr(self._voice, "begin_turn", None)
        if callable(begin):
            begin()
        self._voice.say(text, cached_wav=self._cache.get(text))
        self._voice.wait_until_idle()
        self._body.set_state(RobotState.IDLE)


def run_onboarding(
    *,
    config: Config,
    persona: Persona,
    profile: Profile,
    client: ChatClient,
    source: Any,
    voice: Any,
    body: Any,
    wav_cache: dict[str, Any] | None = None,
) -> Profile:
    """名前をたずねて `profile` を更新し、保存して返す。"""
    speaker = _Speaker(persona, voice, body, wav_cache or {})

    speaker.say("ask_name", emotion=Emotion.URESHII)

    display = reading = ""
    for attempt in range(MAX_ATTEMPTS):
        _set_hint(source, STT_HINT)
        body.set_state(RobotState.LISTENING)
        raw = source.listen()
        _set_hint(source, None)

        if raw is None:  # 中断された
            break
        raw = raw.strip()
        if not raw:
            speaker.say("retry_name", emotion=Emotion.KOMATTA)
            continue

        body.set_state(RobotState.THINKING)
        display, reading, confidence = _normalize_name(client, raw)
        if not display:
            speaker.say("retry_name", emotion=Emotion.KOMATTA)
            continue

        # 実際に読み上げて本人に確認してもらう
        speaker.say("confirm_name", emotion=Emotion.TANOSHII, name=reading or display)
        body.set_state(RobotState.LISTENING)
        answer = (source.listen() or "").strip()

        if _is_yes(answer):
            break
        if _is_no(answer) or attempt < MAX_ATTEMPTS - 1:
            display = reading = ""
            speaker.say("retry_name", emotion=Emotion.KOMATTA)
            continue

    if not display:
        speaker.say("give_up", emotion=Emotion.KOMATTA)
        profile.child = ChildProfile(
            display="きみ", reading="キミ", honorific="", age=config.child.age
        )
        profile.save(config.profile_path)
        return profile

    honorific = _ask_honorific(speaker, source, body, name=reading or display)

    profile.child = ChildProfile(
        display=display,
        reading=reading,
        honorific=honorific,
        age=config.child.age,
    )
    profile.save(config.profile_path)
    speaker.say("done", emotion=Emotion.URESHII, child=profile.child.spoken_name)
    return profile


def _ask_honorific(speaker: _Speaker, source: Any, body: Any, *, name: str) -> str:
    """「くん」か「ちゃん」かを選んでもらう。決まらなければ「くん」。"""
    speaker.say("ask_honorific", emotion=Emotion.TANOSHII, name=name)
    body.set_state(RobotState.LISTENING)
    answer = (source.listen() or "").strip()

    if "ちゃん" in answer:
        return "ちゃん"
    if "くん" in answer or "クン" in answer:
        return "くん"
    if any(word in answer for word in ("どっち", "どちら", "なし", "よびすて")):
        return ""
    return "くん"
