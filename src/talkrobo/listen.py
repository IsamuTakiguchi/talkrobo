"""子供の発話を1つ受け取るインターフェース。

テキストモードではキーボード入力、音声モードでは「録音 → STT」がこれを実装する。
app.py はどちらが入っているかを知らない。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from rich.console import Console

QUIT_WORDS = {"quit", "exit", "q", "ばいばい", "バイバイ", "またね", "おやすみ"}


@runtime_checkable
class InputSource(Protocol):
    """発話を1つ取得する。"""

    def listen(self, on_captured: Callable[[], None] | None = None) -> str | None:
        """子供の発話を返す。会話を終える場合は None。

        `on_captured` は「入力を取り終えた直後・まだ内容が確定する前」に呼ばれる。
        音声モードではここが録音終了の合図になり、相づちの再生を開始する。
        """
        ...

    def close(self) -> None:
        """後始末。"""


class TextInput:
    """キーボードから打ち込んだ文字を発話として扱う（ハード・マイク不要）。"""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def listen(self, on_captured: Callable[[], None] | None = None) -> str | None:
        try:
            text = self._console.input("\n[bold cyan]きみ >[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not text:
            return ""
        if text.lower() in QUIT_WORDS:
            return None

        if on_captured:
            on_captured()
        return text

    def close(self) -> None:
        pass
