"""テスト用の擬似部品。外部依存（API・マイク・スピーカー・GPIO）を持たない。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from talkrobo.config import Config
from talkrobo.llm.client import ReplyMeta, Usage
from talkrobo.llm.memory import ChildProfile, Profile
from talkrobo.persona import Persona
from talkrobo.states import Emotion, RobotState

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg = Config.load(REPO_ROOT / "config" / "config.example.yaml", root=REPO_ROOT)
    cfg.data_dir = tmp_path  # 実データを汚さない
    return cfg


@pytest.fixture
def persona(config: Config) -> Persona:
    return Persona.load(config.persona_path)


@pytest.fixture
def profile() -> Profile:
    return Profile(child=ChildProfile(display="はると", reading="ハルト", honorific="くん", age=6))


class FakeClient:
    """スクリプト済みの返事を1デルタずつ返す擬似 ChatClient。"""

    def __init__(self, replies: list[str] | None = None, *, chunk: int = 3) -> None:
        self.replies = list(replies or [])
        self.chunk = chunk
        self.model = "fake-model"
        self.last = ReplyMeta()
        self.calls: list[list[dict]] = []
        self.refuse = False

    def stream_reply(self, system: str, messages: list[dict]) -> Iterator[str]:
        self.calls.append(messages)
        self.last = ReplyMeta()
        if self.refuse:
            self.last = ReplyMeta(stop_reason="refusal", usage=Usage(), model=self.model)
            return
        reply = self.replies.pop(0) if self.replies else "[ふつう]ピカ。"
        for i in range(0, len(reply), self.chunk):
            yield reply[i : i + self.chunk]
        self.last = ReplyMeta(
            stop_reason="end_turn",
            usage=Usage(input_tokens=100, output_tokens=20),
            model=self.model,
        )

    def complete_json(self, **kwargs):  # pragma: no cover - 既定では使わない
        return None


class FakeVoice:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.turns = 0

    def say(self, text: str, *, cached_wav: Path | None = None) -> None:
        self.said.append(text)

    def begin_turn(self) -> None:
        self.turns += 1

    def is_busy(self) -> bool:
        return False

    def wait_until_idle(self, timeout: float | None = None) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeBody:
    def __init__(self) -> None:
        self.states: list[RobotState] = []
        self.emotions: list[Emotion] = []

    def set_state(self, state: RobotState) -> None:
        self.states.append(state)

    def set_emotion(self, emotion: Emotion) -> None:
        self.emotions.append(emotion)

    def close(self) -> None:
        pass


class ScriptedInput:
    """あらかじめ決めた発話を順に返す。尽きたら None（＝会話終了）。"""

    def __init__(self, utterances: list[str]) -> None:
        self._queue = list(utterances)
        self.hints: list[str | None] = []

    def listen(self, on_captured: Callable[[], None] | None = None) -> str | None:
        if not self._queue:
            return None
        text = self._queue.pop(0)
        if on_captured:
            on_captured()
        return text

    def set_hint(self, hint: str | None) -> None:
        self.hints.append(hint)

    def close(self) -> None:
        pass


class FakeFiller:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def timed_out(self) -> bool:
        return False
