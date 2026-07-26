"""しゃべる側のインターフェース。

`say()` は**ブロックしない**（キューに積むだけ）。
LLM のストリームから文が確定するたびに積んでいき、裏で合成・再生が進む。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Voice(Protocol):
    def say(self, text: str, *, cached_wav: Path | None = None) -> None:
        """発話をキューに積む。`cached_wav` があれば合成を省いてそれを鳴らす。"""

    def is_busy(self) -> bool:
        """合成待ち・再生中のものが残っているか。"""

    def wait_until_idle(self, timeout: float | None = None) -> None:
        """キューが空になるまで待つ。"""

    def stop(self) -> None:
        """キューを捨てて再生を止める。"""

    def close(self) -> None:
        """後始末。"""
