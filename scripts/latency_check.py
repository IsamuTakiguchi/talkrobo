#!/usr/bin/env python
"""「話しかけてから返事が返るまで」を実測する。

マイクは使わない。VOICEVOX で子供の発話を合成し、それを音声認識に通すことで、
録音以降の全工程を機械的に測る。

    録音終了 ─┬─ 相づち（キャッシュ再生）   ← 目標 0.5 秒以内
              └─ 音声認識 → LLM 1文目 → 合成 ← 目標 2.0 秒以内

使い方:
    python scripts/latency_check.py
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from talkrobo.config import Config, get_api_key  # noqa: E402
from talkrobo.llm.client import ChatClient  # noqa: E402
from talkrobo.llm.emotion_tag import EmotionTagExtractor  # noqa: E402
from talkrobo.llm.memory import ChildProfile  # noqa: E402
from talkrobo.llm.sentence_splitter import SentenceSplitter  # noqa: E402
from talkrobo.persona import Persona, build_system_prompt  # noqa: E402
from talkrobo.tts.voicevox import VoicevoxClient, build_wav_cache, decode_wav  # noqa: E402

SAMPLE_UTTERANCES = [
    "きょうね、ようちえんでかけっこしたよ",
    "ピカチュウはなにがすきなの",
    "あそぼう",
]

TARGET_FIRST_REACTION = 0.5
TARGET_FIRST_SENTENCE = 2.0


def main() -> int:
    parser = argparse.ArgumentParser(description="レイテンシの実測")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--repeat", type=int, default=3, help="各項目の試行回数")
    args = parser.parse_args()

    console = Console()
    config = Config.load(args.config)
    persona = Persona.load(config.persona_path)

    try:
        from talkrobo.stt.faster_whisper_stt import FasterWhisperSTT
    except ImportError as exc:
        console.print(f'[red]faster-whisper が必要です: {exc}[/red]\npip install -e ".[audio]"')
        return 1

    tts = VoicevoxClient(config.tts.url, persona.voice, timeout=config.tts.timeout)
    try:
        console.print(f"[dim]VOICEVOX ENGINE {tts.check()}[/dim]")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    # --- 0. 相づち（キャッシュ再生の準備時間） --------------------------
    with console.status("[dim]相づちのキャッシュを確認しています…[/dim]"):
        cache = build_wav_cache(
            tts, persona.all_fillers(), config.filler_cache_dir, persona.source_hash
        )
    ack_samples: list[float] = []
    ack_text = (persona.fillers.get("ack") or ["ピカ？"])[0]
    ack_path = cache.get(ack_text)
    for _ in range(args.repeat):
        start = time.perf_counter()
        if ack_path and ack_path.exists():
            decode_wav(ack_path.read_bytes())
        ack_samples.append(time.perf_counter() - start)

    # --- 1. 音声認識 ----------------------------------------------------
    with console.status("[dim]音声認識モデルを読み込んでいます…[/dim]"):
        stt = FasterWhisperSTT(
            model_size=config.stt.model_size,
            compute_type=config.stt.compute_type,
            device=config.stt.device,
            language=config.stt.language,
        )

    wavs = []
    with console.status("[dim]テスト用の発話を合成しています…[/dim]"):
        for text in SAMPLE_UTTERANCES:
            samples, _rate = decode_wav(tts.synth(text))
            wavs.append((text, samples))

    stt.transcribe(wavs[0][1])  # 初回のウォームアップは計測から外す

    stt_samples: list[float] = []
    for text, samples in wavs:
        start = time.perf_counter()
        recognized = stt.transcribe(samples)
        stt_samples.append(time.perf_counter() - start)
        console.print(f"  [dim]「{text}」→「{recognized}」[/dim]")

    # --- 2. LLM の1文目 + 合成 ------------------------------------------
    client = ChatClient(
        get_api_key(),
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        effort=config.llm.effort,
    )
    child = ChildProfile(display="はると", reading="ハルト", honorific="くん", age=6)
    system = build_system_prompt(persona, child_name=child.call_name, age=child.age, facts=[])

    llm_samples: list[float] = []
    tts_samples: list[float] = []
    for text, _ in wavs:
        extractor = EmotionTagExtractor()
        splitter = SentenceSplitter()
        first_sentence = ""
        start = time.perf_counter()
        for delta in client.stream_reply(system, [{"role": "user", "content": text}]):
            sentences = splitter.feed(extractor.feed(delta))
            if sentences:
                first_sentence = sentences[0]
                break
        llm_samples.append(time.perf_counter() - start)

        if first_sentence:
            start = time.perf_counter()
            tts.synth(first_sentence)
            tts_samples.append(time.perf_counter() - start)
            console.print(f"  [dim]1文目「{first_sentence}」[/dim]")

    # --- 結果 -----------------------------------------------------------
    def med(values: list[float]) -> float:
        return statistics.median(values) if values else 0.0

    stt_med, llm_med, tts_med = med(stt_samples), med(llm_samples), med(tts_samples)
    total = stt_med + llm_med + tts_med
    first_reaction = med(ack_samples)

    table = Table(title=f"レイテンシ実測  model={client.model} / stt={config.stt.model_size}")
    table.add_column("区間")
    table.add_column("中央値", justify="right")
    table.add_row("相づち（キャッシュ読み込み）", f"{first_reaction * 1000:.0f} ms")
    table.add_row("音声認識", f"{stt_med:.2f} s")
    table.add_row("LLM 1文目まで", f"{llm_med:.2f} s")
    table.add_row("1文目の音声合成", f"{tts_med:.2f} s")
    table.add_row("[bold]合計（録音終了→発話開始）[/bold]", f"[bold]{total:.2f} s[/bold]")
    console.print(table)

    ok = True
    if first_reaction > TARGET_FIRST_REACTION:
        console.print(f"[red]最初の反応が {TARGET_FIRST_REACTION} 秒を超えています[/red]")
        ok = False
    if total > TARGET_FIRST_SENTENCE:
        console.print(
            f"[yellow]1文目まで {total:.2f} 秒（目標 {TARGET_FIRST_SENTENCE} 秒）。"
            "  調整の順番: ①相づちの間隔を短く ②stt.model_size を base に "
            "③文分割の閾値を短く[/yellow]"
        )
        ok = False
    if ok:
        console.print("[green]目標を満たしています[/green]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
