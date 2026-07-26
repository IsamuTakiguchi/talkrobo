"""音声で発話を1つ受け取る（きっかけ待ち → 録音 → 音声認識）。

`on_captured` は**録音が終わった直後・音声認識を始める前**に呼ぶ。
ここが「間」を埋める相づちの開始点になる。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


class VoiceInput:
    def __init__(
        self,
        *,
        recorder: Any,
        stt: Any,
        trigger: Any,
        on_record_start: Callable[[], None] | None = None,
    ) -> None:
        self._recorder = recorder
        self._stt = stt
        self._trigger = trigger
        self._on_record_start = on_record_start
        self._hint: str | None = None

    def set_hint(self, hint: str | None) -> None:
        """次の1回の認識に効くヒント（名前を聞く場面などで使う）。"""
        self._hint = hint

    def listen(self, on_captured: Callable[[], None] | None = None) -> str | None:
        if not self._trigger.wait_for_start():
            return None

        if self._on_record_start:
            self._on_record_start()

        audio = self._recorder.record(self._trigger.should_continue)

        # 録音が終わった瞬間に知らせる（音声認識を待たずに相づちを打つため）
        if on_captured:
            on_captured()

        if getattr(audio, "size", 0) == 0:
            return ""
        return self._stt.transcribe(audio, hint=self._hint)

    def close(self) -> None:
        self._trigger.close()
        self._stt.close()
