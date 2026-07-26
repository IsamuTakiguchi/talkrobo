"""音声入力の流れのテスト（マイク不要）。"""

from __future__ import annotations

import numpy as np

from talkrobo.audio.voice_input import VoiceInput


class FakeRecorder:
    def __init__(self, samples: np.ndarray) -> None:
        self._samples = samples
        self.calls = 0

    def record(self, should_continue):
        self.calls += 1
        return self._samples


class FakeSTT:
    def __init__(self, text: str = "こんにちは", events: list[str] | None = None) -> None:
        self.text = text
        self.hints: list[str | None] = []
        self.events = events if events is not None else []

    def transcribe(self, audio, *, hint=None):
        self.hints.append(hint)
        self.events.append("transcribe")
        return self.text

    def close(self):
        pass


class FakeTrigger:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def wait_for_start(self) -> bool:
        return self.allow

    def should_continue(self, elapsed, silence, speech_detected) -> bool:
        return False

    def close(self):
        pass


def build(samples, *, text="こんにちは", allow=True, events=None):
    return VoiceInput(
        recorder=FakeRecorder(samples),
        stt=FakeSTT(text, events),
        trigger=FakeTrigger(allow),
    )


def test_returns_transcribed_text():
    source = build(np.ones(100, dtype="float32"))
    assert source.listen() == "こんにちは"


def test_on_captured_fires_before_transcription():
    """録音が終わった瞬間に相づちを打ちはじめるため、STT より先に呼ばれること。"""
    events: list[str] = []
    source = build(np.ones(100, dtype="float32"), events=events)

    source.listen(on_captured=lambda: events.append("captured"))

    assert events == ["captured", "transcribe"]


def test_silence_returns_empty_without_calling_stt():
    events: list[str] = []
    source = build(np.zeros(0, dtype="float32"), events=events)

    assert source.listen() == ""
    assert "transcribe" not in events


def test_trigger_can_end_the_conversation():
    source = build(np.ones(10, dtype="float32"), allow=False)
    assert source.listen() is None


def test_hint_is_passed_to_stt():
    source = build(np.ones(10, dtype="float32"))
    source.set_hint("なまえは")
    source.listen()

    assert source._stt.hints == ["なまえは"]
