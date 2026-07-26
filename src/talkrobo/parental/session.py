"""会話ログ・利用時間・予算上限を、app が使う2つの部品にまとめる。"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from ..config import Config
from ..llm.client import Usage
from ..states import Emotion
from .budget import BudgetTracker
from .limits import TimeLimiter
from .logger import ConversationLogger


class SessionRecorder:
    """1ターンごとの記録（会話ログ + API 使用量）。"""

    def __init__(
        self,
        logger: ConversationLogger,
        budget: BudgetTracker,
        console: Console,
    ) -> None:
        self._logger = logger
        self._budget = budget
        self._console = console

    def record_user(self, text: str) -> None:
        self._logger.user(text)

    def record_robot(self, text: str, emotion: Emotion) -> None:
        self._logger.robot(text, emotion.value)

    def record_usage(self, model: str, usage: Usage) -> None:
        self._budget.record(model, usage)
        if self._budget.should_warn():
            self._console.print(
                f"[yellow]お知らせ: 今月の API 概算が "
                f"{self._budget.month_yen:.0f}円 に達しました。[/yellow]"
            )


def build_guards(
    config: Config, console: Console
) -> tuple[SessionRecorder, Callable[[], str | None]]:
    """(記録係, 会話を止めるべきか判定する関数) を返す。

    判定関数はペルソナのセリフキー（"time_limit" / "budget_limit" / "quiet_hours"）
    を返す。None なら続行。
    """
    logger = ConversationLogger(config.log_dir)
    budget = BudgetTracker(config)
    limiter = TimeLimiter(config)
    recorder = SessionRecorder(logger, budget, console)

    def should_stop() -> str | None:
        if budget.is_over_limit():
            return "budget_limit"
        return limiter.check()

    return recorder, should_stop
