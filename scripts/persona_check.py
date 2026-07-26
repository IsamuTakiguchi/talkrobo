#!/usr/bin/env python
"""キャラクターが保てているかを自動で評価する。

20個の質問を投げて、返事が次を満たしているかを数える:
  1. 感情タグが正しく付いている（からだの動きがこれに依存する）
  2. 鳴き声が1回以上入っている
  3. 子供の名前がちょうど1回だけ出てくる（0回だと他人行儀、2回以上はくどい）
  4. 3文までに収まっている
  5. 漢字が混ざっていない（6歳児が音で聞いて分かることば）
  6. 「です・ます」調になっていない（ともだちとして話す）
  7. 「トレーナー」などの役割名で呼んでいない

使い方:
    python scripts/persona_check.py [--model claude-opus-5] [--name はると]

90% 未満ならシステムプロンプトを調整する。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from talkrobo.config import Config, get_api_key  # noqa: E402
from talkrobo.llm.client import ChatClient  # noqa: E402
from talkrobo.llm.emotion_tag import EmotionTagExtractor  # noqa: E402
from talkrobo.llm.memory import ChildProfile  # noqa: E402
from talkrobo.persona import Persona, build_system_prompt  # noqa: E402

QUESTIONS = [
    "こんにちは",
    "きょうね、ようちえんでかけっこしたよ",
    "ピカチュウはなにがすきなの？",
    "あそぼう！",
    "ぼく、きょうりゅうがすきなんだ",
    "おなかすいた",
    "ねむいなあ",
    "きのうテレビみたよ",
    "ピカチュウってつよいの？",
    "いもうとがうまれたんだ",
    "そらってなんであおいの？",
    "けんかしちゃった",
    "あしたなにするの？",
    "うたうたって",
    "ぼくのなまえおぼえてる？",
    "おそとであそびたい",
    "こわいゆめみた",
    "ピカチュウのおうちはどこ？",
    "きょうはたのしかった",
    "ばいばい",
]

CRY = re.compile(r"ピカ|ピッカ|チュウ|チュ〜")
SENTENCE_END = re.compile(r"[。！？!?…]")
KANJI = re.compile(r"[一-鿿]")
POLITE = re.compile(r"(です|ます|ました|でした|ください)[。！？!?…]?")
ROLE_WORDS = ("トレーナー", "マスター", "ごしゅじん")

PASS_THRESHOLD = 0.90


def count_sentences(text: str) -> int:
    parts = [p for p in SENTENCE_END.split(text) if p.strip()]
    return len(parts)


def check(reply: str, emotion_ok: bool, name: str) -> dict[str, bool]:
    return {
        "感情タグ": emotion_ok,
        "鳴き声": bool(CRY.search(reply)),
        "名前1回": reply.count(name) == 1,
        "3文まで": 1 <= count_sentences(reply) <= 3,
        "漢字なし": not KANJI.search(reply),
        "ですます無": not POLITE.search(reply),
        "役割名なし": not any(word in reply for word in ROLE_WORDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ペルソナ維持の自動評価")
    parser.add_argument("--model", default=None, help="評価するモデル（既定は config.yaml）")
    parser.add_argument("--name", default="はると", help="子供の名前")
    parser.add_argument("--honorific", default="くん")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    console = Console()
    config = Config.load(args.config)
    persona = Persona.load(config.persona_path)
    child = ChildProfile(
        display=args.name, reading=args.name, honorific=args.honorific, age=config.child.age
    )

    client = ChatClient(
        get_api_key(),
        model=args.model or config.llm.model,
        max_tokens=config.llm.max_tokens,
        effort=config.llm.effort,
    )
    system = build_system_prompt(persona, child_name=child.call_name, age=child.age, facts=[])

    table = Table(title=f"ペルソナ評価  model={client.model}", show_lines=False)
    table.add_column("質問", overflow="fold", max_width=22)
    table.add_column("返事", overflow="fold", max_width=42)
    table.add_column("結果", overflow="fold")

    totals: dict[str, int] = {}
    all_pass = 0

    with console.status("[dim]評価中…[/dim]") as status:
        for index, question in enumerate(QUESTIONS, start=1):
            status.update(f"[dim]評価中… {index}/{len(QUESTIONS)}[/dim]")
            extractor = EmotionTagExtractor()
            body = "".join(
                extractor.feed(delta)
                for delta in client.stream_reply(system, [{"role": "user", "content": question}])
            )
            body += extractor.flush()
            body = body.strip()

            results = check(body, extractor.tag_found, args.name)
            for key, ok in results.items():
                totals[key] = totals.get(key, 0) + (1 if ok else 0)
            if all(results.values()):
                all_pass += 1

            marks = " ".join(
                f"[green]{k}[/green]" if ok else f"[red]{k}[/red]" for k, ok in results.items()
            )
            table.add_row(question, body, marks)

    console.print(table)

    total = len(QUESTIONS)
    console.print("\n[bold]項目ごとの達成率[/bold]")
    for key, count in totals.items():
        ratio = count / total
        color = "green" if ratio >= PASS_THRESHOLD else "red"
        console.print(f"  {key}: [{color}]{count}/{total} ({ratio:.0%})[/{color}]")

    overall = all_pass / total
    color = "green" if overall >= PASS_THRESHOLD else "red"
    console.print(
        f"\n[bold]全項目クリア: [{color}]{all_pass}/{total} ({overall:.0%})[/{color}][/bold]"
    )

    if overall < PASS_THRESHOLD:
        console.print(
            "[yellow]90% を下回りました。"
            "config/personas/*.yaml の speech_style / cry_rule を調整してください。[/yellow]"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
