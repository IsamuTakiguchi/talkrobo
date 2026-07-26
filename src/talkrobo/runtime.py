"""音声モードの部品を組み立てる。

ここだけが sounddevice / faster-whisper / gpiozero に依存する。
`--text` では読み込まれないので、これらが未インストールでもテキスト会話はできる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from .audio.filler import FillerPlayer
from .audio.player import AudioPlayer
from .audio.recorder import Recorder
from .audio.voice_input import VoiceInput
from .config import Config
from .hardware.mock_body import MockBody
from .hardware.trigger import ButtonTrigger, KeyboardTrigger
from .persona import Persona
from .states import RobotState
from .stt.faster_whisper_stt import FasterWhisperSTT
from .tts.voicevox import VoicevoxClient, VoicevoxVoice, build_wav_cache

log = logging.getLogger(__name__)


@dataclass
class VoiceComponents:
    source: Any
    voice: Any
    body: Any
    filler: Any
    wav_cache: dict[str, Path]


def build_voice_components(
    *,
    config: Config,
    persona: Persona,
    console: Console,
    use_pi: bool,
) -> VoiceComponents:
    # --- しゃべる側 -----------------------------------------------------
    client = VoicevoxClient(config.tts.url, persona.voice, timeout=config.tts.timeout)
    version = client.check()  # 起動していなければ分かりやすいエラーで止まる
    console.print(f"[dim]VOICEVOX ENGINE {version} に接続しました[/dim]")

    player = AudioPlayer(device=config.audio.output_device)
    voice = VoicevoxVoice(client, player)

    wav_cache = _build_cache(client, persona, config, console)

    # --- からだ ---------------------------------------------------------
    body = _build_body(persona, config, console, use_pi)

    # --- きく側 ---------------------------------------------------------
    trigger = _build_trigger(config, console, use_pi)

    with console.status("[dim]音声認識モデルを読み込んでいます…[/dim]"):
        stt = FasterWhisperSTT(
            model_size=config.stt.model_size,
            compute_type=config.stt.compute_type,
            device=config.stt.device,
            language=config.stt.language,
        )

    recorder = Recorder(
        samplerate=config.audio.sample_rate,
        max_seconds=config.audio.max_record_seconds,
        device=config.audio.input_device,
        silence_rms=config.audio.silence_rms,
    )
    source = VoiceInput(
        recorder=recorder,
        stt=stt,
        trigger=trigger,
        on_record_start=lambda: body.set_state(RobotState.LISTENING),
    )

    filler = FillerPlayer(
        persona=persona,
        voice=voice,
        config=config.filler,
        wav_cache=wav_cache,
    )

    return VoiceComponents(
        source=source, voice=voice, body=body, filler=filler, wav_cache=wav_cache
    )


# ---------------------------------------------------------------------------


def _build_cache(
    client: VoicevoxClient, persona: Persona, config: Config, console: Console
) -> dict[str, Path]:
    texts = persona.all_fillers()
    pending: list[str] = []

    def on_progress(index: int, total: int, text: str) -> None:
        pending.append(text)

    with console.status("[dim]相づちの音声をつくっています…[/dim]"):
        cache = build_wav_cache(
            client,
            texts,
            config.filler_cache_dir,
            persona.source_hash,
            on_progress=on_progress,
        )
    if pending:
        console.print(f"[dim]相づちを {len(pending)} 件あたらしく合成しました[/dim]")
    return cache


def _build_body(persona: Persona, config: Config, console: Console, use_pi: bool) -> Any:
    if not use_pi:
        return MockBody(persona, console)
    try:
        from .hardware.pi_body import PiBody

        return PiBody(persona, config.hardware)
    except Exception as exc:
        console.print(f"[yellow]実機のからだを使えないので、画面表示に切り替えます:[/yellow] {exc}")
        return MockBody(persona, console)


def _build_trigger(config: Config, console: Console, use_pi: bool) -> Any:
    if not use_pi:
        return KeyboardTrigger(console)
    try:
        return ButtonTrigger(config.hardware.button_pin, console)
    except Exception as exc:
        console.print(f"[yellow]ボタンを使えないので、Enter キーに切り替えます:[/yellow] {exc}")
        return KeyboardTrigger(console)
