#!/usr/bin/env python
"""API キーもマイクも無しで、会話の見た目と動きを確認するデモ。

Claude の代わりに、あらかじめ用意した返事をストリーミングで流します。
本番と同じ会話ループ・同じ文分割・同じ感情タグ処理を通るので、
「返事がどう出て、からだがどう動くか」をそのまま確認できます。

    python scripts/demo.py
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console  # noqa: E402

from talkrobo.app import TalkRobo  # noqa: E402
from talkrobo.config import Config  # noqa: E402
from talkrobo.hardware.mock_body import MockBody  # noqa: E402
from talkrobo.llm.client import ReplyMeta, Usage  # noqa: E402
from talkrobo.llm.memory import ChildProfile, Profile  # noqa: E402
from talkrobo.persona import Persona  # noqa: E402
from talkrobo.tts.print_voice import PrintVoice  # noqa: E402

# 子供の発話と、それに対する返事（本来は Claude が生成する部分）
SCRIPT = [
    (
        "こんにちは",
        "[うれしい]ピカ！ こんにちは、はるとくん！ きょうもあそぼうね！",
    ),
    (
        "きょうね、ようちえんでかけっこしたよ",
        "[たのしい]ピカァ〜！ かけっこしたんだ、いいなあ。はるとくん、はやかった？",
    ),
    (
        "いちばんだったよ",
        "[でんき]ピッカー！ いちばん！？ すごいよ、はるとくん！ ボクもかけっこだいすきなんだ。",
    ),
    (
        "ピカチュウはなにがすきなの？",
        "[うれしい]ボクね、きのみがだいすきなんだ。ケチャップもすき、ピカ！ "
        "はるとくんのすきなたべものはなに？",
    ),
    (
        "ハンバーグ！",
        "[びっくり]ピカッ!? おいしそう！ こんどいっしょにたべたいなあ、ピカ。",
    ),
]

TYPING_DELAY = 0.012  # 1文字ぶんの生成時間（ストリーミングの見た目を再現）


class ScriptedClient:
    """Claude の代わりに、決められた返事を1文字ずつ返す。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.model = "demo（APIは呼びません）"
        self.last = ReplyMeta()

    def stream_reply(self, system: str, messages: list[dict]) -> Iterator[str]:
        reply = self._replies.pop(0) if self._replies else "[ふつう]ピカ。"
        # 本物と同じように、少しずつ届く様子を再現する
        time.sleep(0.35)
        for char in reply:
            time.sleep(TYPING_DELAY)
            yield char
        self.last = ReplyMeta(
            stop_reason="end_turn",
            usage=Usage(input_tokens=1500, output_tokens=70),
            model=self.model,
        )


class ScriptedInput:
    """子供の発話を、打ち込んでいるように見せながら流す。"""

    def __init__(self, utterances: list[str], console: Console) -> None:
        self._queue = list(utterances)
        self._console = console

    def listen(self, on_captured=None) -> str | None:
        if not self._queue:
            return None
        text = self._queue.pop(0)
        self._console.print(f"\n[bold cyan]はるとくん >[/bold cyan] {text}")
        time.sleep(0.3)
        if on_captured:
            on_captured()
        return text

    def close(self) -> None:
        pass


def main() -> int:
    console = Console()
    root = Path(__file__).resolve().parents[1]
    config = Config.load(root / "config" / "config.example.yaml", root=root)
    persona = Persona.load(config.persona_path)

    profile = Profile(
        child=ChildProfile(display="はると", reading="ハルト", honorific="くん", age=6)
    )

    console.print(
        f"\n[bold]{persona.name} デモ[/bold]  "
        "[dim]— API キーもマイクも使いません。返事はあらかじめ用意したものです[/dim]\n"
    )

    robo = TalkRobo(
        config=config,
        persona=persona,
        profile=profile,
        client=ScriptedClient([reply for _, reply in SCRIPT]),
        source=ScriptedInput([text for text, _ in SCRIPT], console),
        voice=PrintVoice(persona.name, console),
        body=MockBody(persona, console),
        console=console,
    )
    try:
        robo.run()
    finally:
        robo.close()

    console.print(
        "\n[dim]本番では ロボット> の各行が音声で読み上げられ、"
        "🙂 の行のとおりに しっぽ・目・ほっぺが動きます。[/dim]"
    )
    console.print("[dim]実際に Claude と会話するには README の「まずテキストで動かす」へ。[/dim]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
