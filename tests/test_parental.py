"""保護者向け機能（会話ログ・利用時間・予算上限）のテスト。"""

from __future__ import annotations

import json
from datetime import datetime

from talkrobo.llm.client import Usage
from talkrobo.parental.budget import BudgetTracker
from talkrobo.parental.limits import TimeLimiter
from talkrobo.parental.logger import ConversationLogger


# ---------------------------------------------------------------------------
# 会話ログ
# ---------------------------------------------------------------------------
def test_conversation_log_is_written(tmp_path):
    logger = ConversationLogger(tmp_path)
    logger.user("こんにちは")
    logger.robot("ピカ！ こんにちは！", "うれしい")

    path = tmp_path / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["role"] == "child"
    assert rows[0]["text"] == "こんにちは"
    assert rows[1]["role"] == "robot"
    assert rows[1]["emotion"] == "うれしい"
    assert "ts" in rows[0]


def test_log_failure_does_not_raise(tmp_path):
    """ログが書けなくても会話は止めない。"""
    logger = ConversationLogger(tmp_path / "file.txt" / "nested")
    (tmp_path / "file.txt").write_text("blocker")
    logger.user("こんにちは")  # 例外を投げないこと


# ---------------------------------------------------------------------------
# 予算
# ---------------------------------------------------------------------------
def test_yen_conversion_uses_the_price_table(config):
    config.budget.usd_jpy = 100.0
    tracker = BudgetTracker(config)
    # haiku: input $1 / output $5 per MTok
    yen = tracker.yen_for("claude-haiku-4-5", Usage(input_tokens=1_000_000))
    assert yen == 100.0

    yen = tracker.yen_for("claude-haiku-4-5", Usage(output_tokens=1_000_000))
    assert yen == 500.0


def test_cached_tokens_are_cheaper(config):
    tracker = BudgetTracker(config)
    plain = tracker.yen_for("claude-opus-5", Usage(input_tokens=100_000))
    cached = tracker.yen_for("claude-opus-5", Usage(cache_read_tokens=100_000))
    assert cached < plain


def test_unknown_model_falls_back_to_a_conservative_price(config):
    tracker = BudgetTracker(config)
    yen = tracker.yen_for("mystery-model", Usage(input_tokens=1_000_000))
    assert yen > 0


def test_usage_is_appended_and_totalled(config):
    tracker = BudgetTracker(config)
    tracker.record("claude-haiku-4-5", Usage(input_tokens=1000, output_tokens=100))
    tracker.record("claude-haiku-4-5", Usage(input_tokens=1000, output_tokens=100))

    rows = [json.loads(line) for line in config.usage_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert tracker.month_yen > 0

    # 別インスタンスでも今月分を読み直せる
    assert BudgetTracker(config).month_yen > 0


def test_over_limit_blocks_conversation(config):
    config.budget.monthly_yen = 0.0001
    tracker = BudgetTracker(config)
    assert not tracker.is_over_limit()

    tracker.record("claude-opus-5", Usage(input_tokens=100_000, output_tokens=10_000))
    assert tracker.is_over_limit()


def test_zero_limit_means_unlimited(config):
    config.budget.monthly_yen = 0
    tracker = BudgetTracker(config)
    tracker.record("claude-opus-5", Usage(input_tokens=10_000_000))
    assert not tracker.is_over_limit()


def test_warning_fires_only_once(config):
    config.budget.monthly_yen = 1.0
    config.budget.warn_at_percent = 50
    tracker = BudgetTracker(config)

    tracker.record("claude-opus-5", Usage(input_tokens=200_000))
    assert tracker.should_warn()
    assert not tracker.should_warn()


# ---------------------------------------------------------------------------
# 利用時間
# ---------------------------------------------------------------------------
def test_quiet_hours_crossing_midnight(config):
    config.limits.quiet_start = "20:00"
    config.limits.quiet_end = "07:00"
    limiter = TimeLimiter(config)

    assert limiter.is_quiet_hours(datetime(2026, 7, 26, 21, 0))
    assert limiter.is_quiet_hours(datetime(2026, 7, 26, 3, 0))
    assert not limiter.is_quiet_hours(datetime(2026, 7, 26, 12, 0))


def test_quiet_hours_within_a_day(config):
    config.limits.quiet_start = "12:00"
    config.limits.quiet_end = "13:00"
    limiter = TimeLimiter(config)

    assert limiter.is_quiet_hours(datetime(2026, 7, 26, 12, 30))
    assert not limiter.is_quiet_hours(datetime(2026, 7, 26, 14, 0))


def test_quiet_hours_disabled_when_blank(config):
    config.limits.quiet_start = ""
    config.limits.quiet_end = ""
    limiter = TimeLimiter(config)
    assert not limiter.is_quiet_hours(datetime(2026, 7, 26, 3, 0))


def test_daily_limit_persists_across_runs(config):
    config.limits.daily_limit_minutes = 30
    limiter = TimeLimiter(config)
    limiter._minutes = 29.9
    limiter.save()

    revived = TimeLimiter(config)
    assert revived.minutes_today >= 29.9


def test_over_limit_reports_time_limit(config):
    config.limits.daily_limit_minutes = 1
    config.limits.quiet_start = ""
    config.limits.quiet_end = ""
    limiter = TimeLimiter(config)
    limiter._minutes = 5.0

    assert limiter.check() == "time_limit"


def test_zero_daily_limit_means_unlimited(config):
    config.limits.daily_limit_minutes = 0
    limiter = TimeLimiter(config)
    limiter._minutes = 9999.0
    assert not limiter.is_over_limit()
