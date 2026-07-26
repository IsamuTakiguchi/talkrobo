"""API 使用量の記録と、月次の予算上限。

毎レスポンスの usage を JSONL に残し、単価表（config.yaml）で円換算する。
単価をコードに埋め込まないのは、価格改定に設定だけで追従できるようにするため。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from ..config import Config, PriceRow
from ..llm.client import Usage

log = logging.getLogger(__name__)

# 単価表に無いモデルが来たときの保守的な既定値（高めに見積もる）
UNKNOWN_PRICE = PriceRow(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25)

# API のレスポンスは日付付きの ID を返すことがある
#   例: claude-haiku-4-5 → claude-haiku-4-5-20251001
# Amazon Bedrock 経由では anthropic. の接頭辞も付く
_DATE_SUFFIX = re.compile(r"-\d{8}$")
_PROVIDER_PREFIX = re.compile(r"^(anthropic|us|eu|apac)\.")


def normalize_model_id(model: str) -> str:
    """レスポンスのモデル ID を、単価表のキー（エイリアス）に揃える。"""
    return _DATE_SUFFIX.sub("", _PROVIDER_PREFIX.sub("", model.strip()))


class BudgetTracker:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._path = config.usage_path
        self._prices = config.budget.prices
        self._usd_jpy = config.budget.usd_jpy
        self._limit_yen = max(0.0, config.budget.monthly_yen)
        self._warn_ratio = max(0, min(100, config.budget.warn_at_percent)) / 100.0
        self._month = datetime.now().strftime("%Y-%m")
        self._month_yen = self._load_month_total()
        self._warned = False

    # ------------------------------------------------------------------
    def price_for(self, model: str) -> PriceRow:
        price = self._prices.get(model)
        if price is None:
            # API は日付付きの ID を返すことがあるので、エイリアスに揃えて引き直す
            price = self._prices.get(normalize_model_id(model))
        if price is None:
            log.warning("単価表に %s がありません。高めの既定値で計算します。", model)
            return UNKNOWN_PRICE
        return price

    def yen_for(self, model: str, usage: Usage) -> float:
        price = self.price_for(model)
        usd = (
            usage.input_tokens * price.input
            + usage.output_tokens * price.output
            + usage.cache_read_tokens * price.cache_read
            + usage.cache_write_tokens * price.cache_write
        ) / 1_000_000
        return usd * self._usd_jpy

    # ------------------------------------------------------------------
    def _load_month_total(self) -> float:
        if not self._path.exists():
            return 0.0
        total = 0.0
        try:
            with self._path.open(encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(row.get("ts", "")).startswith(self._month):
                        total += float(row.get("yen", 0.0))
        except OSError:
            log.exception("usage.jsonl の読み込みに失敗しました")
        return total

    def record(self, model: str, usage: Usage) -> float:
        """1リクエストぶんを記録し、その金額（円）を返す。"""
        yen = self.yen_for(model, usage)
        self._month_yen += yen
        row = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": model,
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read": usage.cache_read_tokens,
            "cache_write": usage.cache_write_tokens,
            "yen": round(yen, 4),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("usage.jsonl の書き込みに失敗しました")
        return yen

    # ------------------------------------------------------------------
    @property
    def month_yen(self) -> float:
        return self._month_yen

    def is_over_limit(self) -> bool:
        return self._limit_yen > 0 and self._month_yen >= self._limit_yen

    def should_warn(self) -> bool:
        """上限の warn_at_percent% を初めて超えたときだけ True。"""
        if self._limit_yen <= 0 or self._warned:
            return False
        if self._month_yen >= self._limit_yen * self._warn_ratio:
            self._warned = True
            return True
        return False

    def summary(self) -> str:
        limit = f" / 上限 {self._limit_yen:.0f}円" if self._limit_yen > 0 else " （上限なし）"
        lines = [
            f"[bold]{self._month} の API 使用量[/bold]",
            f"  概算 {self._month_yen:.1f}円{limit}",
            f"  モデル: {self._config.llm.model}",
            f"  記録先: {self._path}",
        ]
        return "\n".join(lines)


def find_usage_path(config: Config) -> Path:
    return config.usage_path
