"""Windows on ARM 対策のテスト。

ARM 版 Windows で x64 版 Python を動かすと、sounddevice が arm64 用の DLL を
選んでしまい読み込めない。platform.machine() がプロセス側のアーキテクチャを
返すようになっているかを見る。
"""

from __future__ import annotations

import os
import platform
import sys

from talkrobo.audio import _win_arm
from talkrobo.audio._win_arm import process_architecture, use_process_architecture


def as_windows(monkeypatch, *, build: str, machine: str, w6432: str | None = None):
    """Windows 環境を模す。"""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(_win_arm.sysconfig, "get_platform", lambda: build)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setattr(platform, "_uname_cache", None, raising=False)
    if w6432 is None:
        monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)
    else:
        monkeypatch.setenv("PROCESSOR_ARCHITEW6432", w6432)


def test_no_op_on_non_windows(monkeypatch):
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")
    assert use_process_architecture() is False
    assert os.environ["PROCESSOR_ARCHITEW6432"] == "ARM64"


def test_process_architecture_reads_the_python_build(monkeypatch):
    monkeypatch.setattr(_win_arm.sysconfig, "get_platform", lambda: "win-amd64")
    assert process_architecture() == "AMD64"

    monkeypatch.setattr(_win_arm.sysconfig, "get_platform", lambda: "win-arm64")
    assert process_architecture() == "ARM64"

    monkeypatch.setattr(_win_arm.sysconfig, "get_platform", lambda: "linux-x86_64")
    assert process_architecture() is None


def test_emulated_x64_on_arm_windows_is_corrected(monkeypatch):
    """x64 Python なのに machine() が ARM64 を返す状況を直す。"""
    as_windows(monkeypatch, build="win-amd64", machine="ARM64", w6432="ARM64")

    assert use_process_architecture() is True
    assert platform.machine().upper() == "AMD64"


def test_correction_works_even_without_the_env_var(monkeypatch):
    """環境変数を消しても直らない環境でも、最終的に AMD64 を返すこと。"""
    as_windows(monkeypatch, build="win-amd64", machine="ARM64", w6432=None)

    assert use_process_architecture() is True
    assert platform.machine().upper() == "AMD64"


def test_native_arm64_windows_is_left_alone(monkeypatch):
    """ARM64 ネイティブの Python なら arm64 DLL が正しいので、さわらない。"""
    as_windows(monkeypatch, build="win-arm64", machine="ARM64")

    assert use_process_architecture() is False
    assert platform.machine().upper() == "ARM64"


def test_ordinary_x64_windows_is_left_alone(monkeypatch):
    as_windows(monkeypatch, build="win-amd64", machine="AMD64")

    assert use_process_architecture() is False


def test_unknown_build_is_left_alone(monkeypatch):
    """想定外のビルドでは、勝手に値を書き換えない。"""
    as_windows(monkeypatch, build="win-something", machine="ARM64")

    assert use_process_architecture() is False
    assert platform.machine().upper() == "ARM64"
