"""コマンドライン入口。

python -m talkrobo --text     テキストで会話（マイク・スピーカー・ハード不要）
python -m talkrobo --mock     PC のマイク／スピーカーで音声会話
python -m talkrobo            Raspberry Pi 実機（ボタン・サーボ・LED）
python -m talkrobo --setup    名前を設定しなおす
python -m talkrobo --usage    今月の API 使用量を表示
python -m talkrobo --devices  オーディオデバイス一覧
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console

from .app import TalkRobo
from .config import Config, get_api_key
from .hardware.mock_body import MockBody
from .listen import TextInput
from .llm.client import ChatClient
from .llm.memory import load_or_build_profile, save_session_memory
from .llm.onboarding import run_onboarding
from .parental.session import build_guards
from .persona import Persona
from .tts.print_voice import PrintVoice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="talkrobo",
        description="子供向け 会話できる人形ロボット",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="テキストで会話（音声・ハード不要）")
    mode.add_argument("--mock", action="store_true", help="PC のマイク／スピーカーで音声会話")

    parser.add_argument("--config", type=Path, default=None, help="設定ファイルのパス")
    parser.add_argument("--setup", action="store_true", help="名前を設定しなおす")
    parser.add_argument("--usage", action="store_true", help="今月の API 使用量を表示して終了")
    parser.add_argument("--devices", action="store_true", help="オーディオデバイス一覧を表示")
    parser.add_argument("-v", "--verbose", action="store_true", help="ログを詳しく出す")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    console = Console()

    if args.devices:
        return _show_devices(console)

    try:
        config = Config.load(args.config)
        persona = Persona.load(config.persona_path)
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"[red]設定エラー:[/red] {exc}")
        return 1

    if args.usage:
        return _show_usage(console, config)

    try:
        api_key = get_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    client = ChatClient(
        api_key,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        effort=config.llm.effort,
    )

    text_mode = args.text
    body = MockBody(persona, console)
    wav_cache: dict[str, Path] = {}
    filler = None

    if text_mode:
        source = TextInput(console)
        voice = PrintVoice(persona.name, console)
        _print_text_mode_help(console, persona)
    else:
        try:
            from .runtime import build_voice_components
        except ImportError as exc:
            console.print(
                f"[red]音声モードに必要なライブラリがありません:[/red] {exc}\n"
                '`pip install -e ".[audio]"` を実行するか、`--text` を使ってください。'
            )
            return 1
        try:
            components = build_voice_components(
                config=config, persona=persona, console=console, use_pi=not args.mock
            )
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        source = components.source
        voice = components.voice
        body = components.body
        filler = components.filler
        wav_cache = components.wav_cache

    profile, needs_onboarding = load_or_build_profile(config)
    if args.setup:
        needs_onboarding = True

    if needs_onboarding:
        profile = run_onboarding(
            config=config,
            persona=persona,
            profile=profile,
            client=client,
            source=source,
            voice=voice,
            body=body,
            wav_cache=wav_cache,
        )
        if args.setup:
            console.print(f"[green]なまえを設定しました:[/green] {profile.child.call_name}")
            voice.close()
            source.close()
            body.close()
            return 0

    # 保護者向けの記録係と、会話を打ち切る判定（時間制限・予算上限）
    recorder, should_stop = build_guards(config, console)

    robo = TalkRobo(
        config=config,
        persona=persona,
        profile=profile,
        client=client,
        source=source,
        voice=voice,
        body=body,
        filler=filler,
        recorder=recorder,
        wav_cache=wav_cache,
        console=console,
        should_stop=should_stop,
    )
    try:
        robo.run()
    finally:
        robo.close()

    # セッション終了後に1回だけ記憶を抽出する（会話中のレイテンシに影響させない）
    added = save_session_memory(config, client, profile, robo.history)
    if added:
        console.print(f"[dim]（{added}件、おぼえました）[/dim]")

    return 0


def _print_text_mode_help(console: Console, persona: Persona) -> None:
    console.print(
        f"\n[bold]{persona.name}[/bold] とテキストで会話します。"
        "  [dim]終わるときは「ばいばい」または Ctrl-C[/dim]\n"
    )


def _show_devices(console: Console) -> int:
    # 音声まわりの不具合はアーキテクチャの食い違いが原因のことがあるので先に出す
    import platform
    import sysconfig

    from .audio import use_process_architecture  # 読み込み前に環境を整える

    use_process_architecture()
    console.print(
        f"[dim]Python: {platform.python_version()} / ビルド: {sysconfig.get_platform()}"
        f" / machine: {platform.machine()}[/dim]\n"
    )

    try:
        import sounddevice as sd
    except ImportError:
        console.print('[red]sounddevice がありません。`pip install -e ".[audio]"`[/red]')
        return 1
    except OSError as exc:
        console.print(f"[red]音声ライブラリを読み込めません:[/red] {exc}")
        return 1
    console.print(str(sd.query_devices()))
    return 0


def _show_usage(console: Console, config: Config) -> int:
    from .parental.budget import BudgetTracker

    tracker = BudgetTracker(config)
    console.print(tracker.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
