"""利用時間の制限（1日あたりの分数と、おやすみ時間帯）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time

from ..config import Config

log = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        log.warning("時刻の書式が不正です: %r （HH:MM で書いてください）", value)
        return None


class TimeLimiter:
    """今日どれだけ遊んだかを数え、上限とおやすみ時間帯を判定する。"""

    def __init__(self, config: Config) -> None:
        self._limit_minutes = max(0, config.limits.daily_limit_minutes)
        self._quiet_start = _parse_hhmm(config.limits.quiet_start)
        self._quiet_end = _parse_hhmm(config.limits.quiet_end)
        self._path = config.data_path / "playtime.json"
        self._today = datetime.now().strftime("%Y-%m-%d")
        self._minutes = self._load()
        self._last_tick = datetime.now()

    # ------------------------------------------------------------------
    def _load(self) -> float:
        if not self._path.exists():
            return 0.0
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("date") == self._today:
                return float(data.get("minutes", 0.0))
        except (OSError, ValueError):
            log.exception("playtime.json の読み込みに失敗しました")
        return 0.0

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"date": self._today, "minutes": round(self._minutes, 2)}),
                encoding="utf-8",
            )
        except OSError:
            log.exception("playtime.json の書き込みに失敗しました")

    # ------------------------------------------------------------------
    def tick(self) -> None:
        """前回の呼び出しからの経過を加算する。"""
        now = datetime.now()
        elapsed = (now - self._last_tick).total_seconds() / 60.0
        self._last_tick = now
        # 長時間の放置は遊んでいたとみなさない（上限5分）
        self._minutes += min(elapsed, 5.0)

    def is_quiet_hours(self, now: datetime | None = None) -> bool:
        if self._quiet_start is None or self._quiet_end is None:
            return False
        current = (now or datetime.now()).time()
        if self._quiet_start <= self._quiet_end:
            return self._quiet_start <= current < self._quiet_end
        # 20:00〜07:00 のように日付をまたぐ場合
        return current >= self._quiet_start or current < self._quiet_end

    def is_over_limit(self) -> bool:
        return self._limit_minutes > 0 and self._minutes >= self._limit_minutes

    @property
    def minutes_today(self) -> float:
        return self._minutes

    def check(self) -> str | None:
        """止めるべきならペルソナのセリフキーを返す。"""
        self.tick()
        self.save()
        if self.is_quiet_hours():
            return "quiet_hours"
        if self.is_over_limit():
            return "time_limit"
        return None
