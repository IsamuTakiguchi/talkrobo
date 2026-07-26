"""Windows on ARM（Copilot+ PC など）で音声ライブラリを読めるようにする。

ARM 版 Windows で x64 版の Python を動かすと、Windows はプロセスに次の
2つの環境変数を渡す。

    PROCESSOR_ARCHITECTURE = AMD64   ← いま動いているプロセスのアーキテクチャ
    PROCESSOR_ARCHITEW6432 = ARM64   ← OS のアーキテクチャ

`platform.machine()` は後者を優先するため「ARM64 マシン」と判定される。
sounddevice はその結果を見て arm64 用の DLL を選ぶが、実際に動いているのは
x64 プロセスなので読み込めず、次のエラーになる。

    OSError: cannot load library '...libportaudioarm64.dll': error 0x7e

x64 版 Python を使うのは faster-whisper（ctranslate2）に Windows ARM64 用の
ビルドが無いためで、エミュレーションで動かすのが現実的な選択肢になる。
そこで sounddevice を import する前に、プロセス側のアーキテクチャが見える
ようにしておく。
"""

from __future__ import annotations

import logging
import os
import platform
import sys

log = logging.getLogger(__name__)


def use_process_architecture() -> bool:
    """`platform.machine()` がプロセス側のアーキテクチャを返すようにする。

    変更した場合だけ True を返す。Windows 以外や、通常の x64 / ARM64 環境
    （2つの環境変数が食い違っていない）では何もしない。
    """
    if sys.platform != "win32":
        return False

    native = os.environ.get("PROCESSOR_ARCHITEW6432", "").strip()
    process = os.environ.get("PROCESSOR_ARCHITECTURE", "").strip()
    if not native or not process or native.upper() == process.upper():
        return False

    os.environ.pop("PROCESSOR_ARCHITEW6432", None)
    # すでに platform が値を確定させていたら、次回に作り直させる
    if getattr(platform, "_uname_cache", None) is not None:
        platform._uname_cache = None

    log.info(
        "Windows on ARM を検出しました（OS=%s / プロセス=%s）。"
        "プロセス側のアーキテクチャで音声ライブラリを読み込みます。",
        native,
        process,
    )
    return True
