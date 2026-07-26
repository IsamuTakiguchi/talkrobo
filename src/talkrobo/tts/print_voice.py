"""ターミナルに文字を出すだけの Voice。テキストモード用。

実際の VOICEVOX 版と同じく「文が確定するたびに1行ずつ」出るので、
ストリーミングで喋りはじめる挙動をそのまま目で確認できる。
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console


class PrintVoice:
    def __init__(self, name: str = "ロボット", console: Console | None = None) -> None:
        self._name = name
        self._console = console or Console()
        self._started = False

    def say(self, text: str, *, cached_wav: Path | None = None) -> None:
        text = text.strip()
        if not text:
            return
        if not self._started:
            self._console.print(f"[bold yellow]{self._name} >[/bold yellow] {text}")
            self._started = True
        else:
            # 2文目以降は続きとして少し下げて表示する
            indent = " " * (len(self._name) + 2)
            self._console.print(f"{indent}{text}")

    def begin_turn(self) -> None:
        """1ターンの表示をリセットする（app から呼ぶ）。"""
        self._started = False

    def is_busy(self) -> bool:
        return False

    def wait_until_idle(self, timeout: float | None = None) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass
