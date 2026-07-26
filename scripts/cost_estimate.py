#!/usr/bin/env python
"""実際のトークン数を測って、月額の見込みを出す。

日本語のトークン数は推定が当てにならないので、`count_tokens` で実測する。
出力トークン（thinking を含む）はモデルによって大きく変わるため、
既定では各モデルに1回だけ実際に問い合わせて測る（数円もかからない）。

使い方:
    python scripts/cost_estimate.py              # 実測（推奨）
    python scripts/cost_estimate.py --no-live    # 入力だけ実測、出力は仮定値
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from talkrobo.config import Config, get_api_key  # noqa: E402
from talkrobo.llm.client import ChatClient, caps_for  # noqa: E402
from talkrobo.llm.memory import ChildProfile, History  # noqa: E402
from talkrobo.persona import Persona, build_system_prompt  # noqa: E402

# 1日あたりのターン数のシナリオ
SCENARIOS = [("軽め", 20), ("標準", 40), ("ヘビー", 80)]
DAYS_PER_MONTH = 30
# --no-live のときの出力トークン仮定値（thinking 込み）
ASSUMED_OUTPUT = {"none": 70, "adaptive": 220}

SAMPLE_TURNS = [
    ("こんにちは", "ピカ！ こんにちは、はるとくん！ きょうもあそぼうね！"),
    ("きょうようちえんでかけっこしたよ", "ピカァ〜！ すごいね！ はやかった？"),
    ("いちばんだったよ", "ピッカー！ すごいすごい！ ボクもかけっこだいすきなんだ。"),
    ("ピカチュウはなにがすきなの？", "ボクね、きのみがだいすき！ ケチャップもすきなんだ、ピカ！"),
    ("ぼくはハンバーグがすき", "へぇ〜！ おいしそうだね、はるとくん。ピカ！"),
    ("あしたなにする？", "うーん、ピカ…。おそとでかけっこしたいなあ！"),
    ("いいね", "ピカァ！ たのしみだね！"),
    ("ねむくなってきた", "ピカ…。ゆっくりやすんでね、はるとくん。"),
]


def build_sample(config: Config, persona: Persona) -> tuple[str, list[dict]]:
    child = ChildProfile(display="はると", reading="ハルト", honorific="くん", age=6)
    system = build_system_prompt(
        persona,
        child_name=child.call_name,
        age=child.age,
        facts=["きょうりゅうがすき", "いもうとの名前はさくら", "ようちえんのねんちょうさん"],
    )
    history = History(max_turns=config.llm.history_turns)
    for child_text, robot_text in SAMPLE_TURNS:
        history.add_user(child_text)
        history.add_assistant(robot_text)
    history.add_user("あのね、きょうすごいことがあったんだ")
    return system, history.messages


def main() -> int:
    parser = argparse.ArgumentParser(description="API 費用の実測と月額試算")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="実際の問い合わせをせず、出力トークンは仮定値を使う",
    )
    args = parser.parse_args()

    console = Console()
    config = Config.load(args.config)
    persona = Persona.load(config.persona_path)
    system, messages = build_sample(config, persona)
    api_key = get_api_key()

    models = list(config.budget.prices) or [config.llm.model]
    usd_jpy = config.budget.usd_jpy

    table = Table(title=f"1ターンあたりのコスト（$1={usd_jpy:.0f}円）")
    table.add_column("モデル")
    table.add_column("入力tok", justify="right")
    table.add_column("出力tok", justify="right")
    table.add_column("キャッシュ", justify="center")
    table.add_column("1ターン", justify="right")
    for label, _ in SCENARIOS:
        table.add_column(f"{label}/月", justify="right")

    for model in models:
        price = config.budget.prices.get(model)
        if price is None:
            continue
        caps = caps_for(model)
        client = ChatClient(api_key, model=model, max_tokens=config.llm.max_tokens)

        try:
            input_tokens = client.count_tokens(system=system, messages=messages)
        except Exception as exc:
            console.print(f"[yellow]{model}: トークン数を測れませんでした ({exc})[/yellow]")
            continue

        if args.no_live:
            output_tokens = ASSUMED_OUTPUT.get(caps.thinking, 100)
        else:
            for _ in client.stream_reply(system, messages):
                pass
            output_tokens = client.last.usage.output_tokens or 1

        # システムプロンプトがキャッシュ最小長に届くかどうか
        cacheable = input_tokens >= caps.cache_min_tokens
        cache_mark = "○" if cacheable else "×"

        usd = (input_tokens * price.input + output_tokens * price.output) / 1_000_000
        per_turn = usd * usd_jpy

        row = [
            model,
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            cache_mark,
            f"{per_turn:.2f}円",
        ]
        for _, turns in SCENARIOS:
            row.append(f"{per_turn * turns * DAYS_PER_MONTH:,.0f}円")
        table.add_row(*row)

    console.print(table)
    console.print(
        "\n[dim]キャッシュ○ … システムプロンプトがそのモデルの最小長に届き、"
        "2回目以降の入力が約1/10になる（上の金額はキャッシュ無しの上限値）[/dim]"
    )
    console.print(
        f"[dim]現在の設定: model={config.llm.model} / "
        f"history_turns={config.llm.history_turns} / "
        f"月上限={config.budget.monthly_yen:.0f}円[/dim]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
