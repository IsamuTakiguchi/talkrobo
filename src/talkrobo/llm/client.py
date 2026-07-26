"""Claude API のラッパ。

モデル世代ごとに thinking / effort / キャッシュの仕様が違うので、
capability テーブルで吸収する（ここを間違えると 400 エラーになる）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import anthropic

log = logging.getLogger(__name__)

# thinking の扱い
THINKING_NONE = "none"  # thinking を渡さない（思考なし・最速・最安）
THINKING_ADAPTIVE = "adaptive"  # {"type": "adaptive"} + effort


@dataclass(frozen=True)
class ModelCaps:
    """モデルごとの API 仕様の違い。"""

    thinking: str
    supports_effort: bool
    # プロンプトキャッシュが成立する最小トークン数（これ未満だと無言で効かない）
    cache_min_tokens: int


MODEL_CAPS: dict[str, ModelCaps] = {
    "claude-haiku-4-5": ModelCaps(THINKING_NONE, supports_effort=False, cache_min_tokens=4096),
    "claude-sonnet-5": ModelCaps(THINKING_ADAPTIVE, supports_effort=True, cache_min_tokens=1024),
    "claude-opus-5": ModelCaps(THINKING_ADAPTIVE, supports_effort=True, cache_min_tokens=512),
}

# 未知のモデル名が来たときの保守的な既定値
FALLBACK_CAPS = ModelCaps(THINKING_NONE, supports_effort=False, cache_min_tokens=4096)


def caps_for(model: str) -> ModelCaps:
    return MODEL_CAPS.get(model, FALLBACK_CAPS)


@dataclass
class Usage:
    """1リクエストぶんのトークン使用量。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @classmethod
    def from_response(cls, usage: Any) -> Usage:
        return cls(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


@dataclass
class ReplyMeta:
    """ストリーム完了後に分かる情報。"""

    stop_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    model: str = ""

    @property
    def refused(self) -> bool:
        """安全機構による拒否。content を読む前に必ずこれを見る。"""
        return self.stop_reason == "refusal"


class ChatClient:
    """会話用の Claude クライアント。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-haiku-4-5",
        max_tokens: int = 300,
        effort: str = "low",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.caps = caps_for(model)
        # 直近のストリームの結果。stream_reply() を消費し終えたあとに読む
        self.last: ReplyMeta = ReplyMeta()

    # ------------------------------------------------------------------
    def _base_kwargs(self, system: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # システムプロンプトは変化しにくいのでキャッシュ対象にする。
            # 最小トークン数に満たないモデル（haiku 等）では無言で無視されるだけで
            # エラーにはならないため、常に付けてよい。
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
        }
        if self.caps.thinking == THINKING_ADAPTIVE:
            kwargs["thinking"] = {"type": "adaptive"}
            if self.caps.supports_effort:
                kwargs["output_config"] = {"effort": self.effort}
        return kwargs

    # ------------------------------------------------------------------
    def stream_reply(self, system: str, messages: list[dict[str, Any]]) -> Iterator[str]:
        """返事をストリーミングで返す。

        消費し終えたあと `self.last` に stop_reason と usage が入る。
        """
        self.last = ReplyMeta()
        kwargs = self._base_kwargs(system, messages)

        with self._client.messages.stream(**kwargs) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()

        self.last = ReplyMeta(
            stop_reason=final.stop_reason,
            usage=Usage.from_response(final.usage),
            model=final.model,
        )
        if self.last.refused:
            log.info("Claude が応答を拒否しました (stop_reason=refusal)")

    # ------------------------------------------------------------------
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 256,
    ) -> dict[str, Any] | None:
        """構造化出力で JSON を1回だけ取る（名前の正規化・記憶の抽出に使う）。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APIError:
            log.warning("構造化出力に失敗したため、通常のテキスト生成にフォールバックします")
            kwargs.pop("output_config")
            kwargs["system"] = system + "\n\n必ず JSON だけを出力すること。説明は書かない。"
            try:
                response = self._client.messages.create(**kwargs)
            except anthropic.APIError:
                log.exception("JSON 生成に失敗しました")
                return None

        self.last = ReplyMeta(
            stop_reason=response.stop_reason,
            usage=Usage.from_response(response.usage),
            model=response.model,
        )
        if self.last.refused:
            return None

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return _loads_lenient(text)

    # ------------------------------------------------------------------
    def count_tokens(self, *, system: str, messages: list[dict[str, Any]]) -> int:
        """実際のトークン数を測る（コスト試算用）。"""
        result = self._client.messages.count_tokens(
            model=self.model,
            system=system,
            messages=messages,
        )
        return result.input_tokens


def _loads_lenient(text: str) -> dict[str, Any] | None:
    """前後に余計な文字が付いていても JSON を拾う。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    log.warning("JSON として解釈できませんでした: %r", text[:200])
    return None
