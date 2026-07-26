"""テキストモード用のダミー STT。

テキスト入力では `InputSource` が既に文字を返しているため、
STT は本来不要。`--text` と `--mock` でコードを共通化するために置いている。
"""

from __future__ import annotations

from typing import Any


class TextSTT:
    def transcribe(self, audio: Any, *, hint: str | None = None) -> str:
        return str(audio or "")

    def close(self) -> None:
        pass
