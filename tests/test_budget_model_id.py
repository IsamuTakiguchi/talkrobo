"""モデル ID の揺れを吸収できているかのテスト。

API のレスポンスは日付付きの ID（claude-haiku-4-5-20251001）を返すのに、
単価表はエイリアス（claude-haiku-4-5）で書かれている。ここが噛み合わないと
高めの既定値で計算され、予算上限が早く発動してしまう。
"""

from __future__ import annotations

from talkrobo.llm.client import Usage
from talkrobo.parental.budget import BudgetTracker, normalize_model_id


def test_normalize_strips_date_suffix():
    assert normalize_model_id("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert normalize_model_id("claude-opus-4-5-20251101") == "claude-opus-4-5"


def test_normalize_strips_provider_prefix():
    assert normalize_model_id("anthropic.claude-opus-5") == "claude-opus-5"
    assert normalize_model_id("us.anthropic.claude-opus-5") == "anthropic.claude-opus-5"


def test_normalize_leaves_plain_alias_alone():
    assert normalize_model_id("claude-haiku-4-5") == "claude-haiku-4-5"
    assert normalize_model_id("claude-opus-5") == "claude-opus-5"


def test_dated_model_id_uses_the_alias_price(config):
    """日付付きの ID でも、エイリアスの単価で計算されること。"""
    tracker = BudgetTracker(config)
    usage = Usage(input_tokens=1_000_000)

    dated = tracker.yen_for("claude-haiku-4-5-20251001", usage)
    alias = tracker.yen_for("claude-haiku-4-5", usage)

    assert dated == alias


def test_dated_model_id_is_not_charged_at_the_fallback_rate(config):
    """既定値（opus 相当）で計算されていないこと＝実際より高く見積もらない。"""
    tracker = BudgetTracker(config)
    usage = Usage(input_tokens=1_000_000)

    dated = tracker.yen_for("claude-haiku-4-5-20251001", usage)
    fallback = tracker.yen_for("まったく知らないモデル", usage)

    assert dated < fallback


def test_truly_unknown_model_still_falls_back(config):
    tracker = BudgetTracker(config)
    assert tracker.yen_for("gpt-something-20240101", Usage(input_tokens=1_000_000)) > 0
