"""Windows on ARM（Copilot+ PC など）で音声ライブラリを読めるようにする。

ARM 版 Windows で x64 版の Python を動かすと、sounddevice が arm64 用の DLL を
選んでしまい、x64 プロセスに読み込めずに落ちる。

    OSError: cannot load library '...libportaudioarm64.dll': error 0x7e

sounddevice の判定はこうなっている（sounddevice.py）::

    if _platform.machine().lower() in ('arm64', 'aarch64'):
        _platform_suffix = 'arm64'
    else:
        _platform_suffix = _platform.architecture()[0]   # '64bit'

`platform.machine()` は Windows では `PROCESSOR_ARCHITEW6432`（**OS** の
アーキテクチャ）を優先するため、x64 エミュレーションで動いていても "ARM64" を
返してしまう。

x64 版 Python を使うのは、faster-whisper が依存する ctranslate2 に
Windows ARM64 用のビルドが無いためで、エミュレーションで動かすのが現実的な
選択肢になる。

判定には `sysconfig.get_platform()` を使う。これは Python 自身のビルドを表す
ので、環境変数の挙動に左右されない（soundfile が同じ方法で正しく動いている）。
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import sysconfig

log = logging.getLogger(__name__)

# sysconfig の値 → platform.machine() が返すべき文字列
_WINDOWS_ARCH = {
    "win-amd64": "AMD64",
    "win-arm64": "ARM64",
    "win32": "X86",
}


def process_architecture() -> str | None:
    """いま動いている Python 自身のアーキテクチャ。判定できなければ None。"""
    return _WINDOWS_ARCH.get(sysconfig.get_platform())


def use_process_architecture() -> bool:
    """`platform.machine()` がプロセス側のアーキテクチャを返すようにする。

    変更した場合だけ True を返す。Windows 以外や、すでに食い違いが無い環境
    （通常の x64 Windows、ARM64 ネイティブ Python）では何もしない。
    """
    if sys.platform != "win32":
        return False

    arch = process_architecture()
    if arch is None:
        return False
    if platform.machine().upper() == arch:
        return False  # 食い違っていない

    log.info(
        "Windows on ARM を検出しました（platform.machine()=%s / プロセス=%s）。"
        "プロセス側のアーキテクチャで音声ライブラリを読み込みます。",
        platform.machine(),
        arch,
    )

    # 1. 誤判定の原因になっている環境変数を、このプロセスから外す
    os.environ.pop("PROCESSOR_ARCHITEW6432", None)
    if getattr(platform, "_uname_cache", None) is not None:
        platform._uname_cache = None

    if platform.machine().upper() == arch:
        return True

    # 2. それでも直らない環境のための保険。
    #    プロセスの実体に合わせるだけなので、正しい値を返すことに変わりはない
    platform.machine = lambda: arch  # type: ignore[assignment]
    return True
