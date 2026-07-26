"""音声認識のインターフェース。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class STT(Protocol):
    def transcribe(self, audio: Any, *, hint: str | None = None) -> str:
        """録音データ（float32 のモノラル配列）を文字にする。

        `hint` は認識のバイアス（名前を聞く場面で「なまえは」を渡すなど）。
        """

    def close(self) -> None:
        """後始末。"""
