"""発話のきっかけ（いつ録音を始めて、いつ終えるか）。

実機は押しボタン（押している間だけ録音）、PC は Enter キー＋無音検知。
録音の終了条件だけが違うので、そこを `should_continue()` で吸収する。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rich.console import Console

from ..listen import QUIT_WORDS

# 話し始める前に許す無音の長さ（これを超えたら「何も言わなかった」とみなす）
LEADING_GRACE_SEC = 4.0
# 話し終わったと判断する無音の長さ
TRAILING_SILENCE_SEC = 1.0


@runtime_checkable
class Trigger(Protocol):
    def wait_for_start(self) -> bool:
        """録音を始めてよくなるまで待つ。False を返すと会話を終了する。"""

    def should_continue(self, elapsed: float, silence: float, speech_detected: bool) -> bool:
        """録音を続けるか。`silence` は末尾の連続無音秒数。"""

    def close(self) -> None: ...


class KeyboardTrigger:
    """Enter キーで録音開始、しゃべり終わり（無音）で自動終了。"""

    def __init__(
        self,
        console: Console | None = None,
        *,
        leading_grace: float = LEADING_GRACE_SEC,
        trailing_silence: float = TRAILING_SILENCE_SEC,
    ) -> None:
        self._console = console or Console()
        self._leading_grace = leading_grace
        self._trailing_silence = trailing_silence

    def wait_for_start(self) -> bool:
        try:
            answer = self._console.input(
                "\n[dim]Enter を押して話しかけてね（終わるときは「ばいばい」＋Enter）[/dim] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.lower() not in QUIT_WORDS

    def should_continue(self, elapsed: float, silence: float, speech_detected: bool) -> bool:
        if not speech_detected:
            # まだ何も聞こえていない間は、少し長めに待つ
            return elapsed < self._leading_grace
        return silence < self._trailing_silence

    def close(self) -> None:
        pass


class ButtonTrigger:
    """GPIO の押しボタン。押している間だけ録音する（誤作動しない・常時録音しない）。"""

    def __init__(self, pin: int, console: Console | None = None) -> None:
        from gpiozero import Button  # 実機でのみ import する

        self._button = Button(pin, pull_up=True, bounce_time=0.05)
        self._console = console or Console()

    def wait_for_start(self) -> bool:
        self._button.wait_for_press()
        return True

    def should_continue(self, elapsed: float, silence: float, speech_detected: bool) -> bool:
        return self._button.is_pressed

    def close(self) -> None:
        try:
            self._button.close()
        except Exception:  # pragma: no cover - 実機依存
            pass
