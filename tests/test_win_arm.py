"""Windows on ARM 対策のテスト。

ARM 版 Windows で x64 版 Python を動かすと、sounddevice が arm64 用の DLL を
選んでしまい読み込めない。その原因になる環境変数を無効化できているかを見る。
"""

from __future__ import annotations

import platform
import sys

from talkrobo.audio._win_arm import use_process_architecture


def test_no_op_on_non_windows(monkeypatch):
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")

    assert use_process_architecture() is False
    # 環境はさわらない
    import os

    assert os.environ["PROCESSOR_ARCHITEW6432"] == "ARM64"


def test_emulated_x64_on_arm_windows_is_corrected(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.setattr(platform, "_uname_cache", "stale", raising=False)

    assert use_process_architecture() is True

    import os

    # ARM64 と誤判定させていた変数が消え、プロセス側の AMD64 が見えるようになる
    assert "PROCESSOR_ARCHITEW6432" not in os.environ
    assert os.environ["PROCESSOR_ARCHITECTURE"] == "AMD64"
    assert platform._uname_cache is None


def test_native_arm64_windows_is_left_alone(monkeypatch):
    """ARM64 ネイティブの Python なら arm64 DLL が正しいので、さわらない。"""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "ARM64")
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)

    assert use_process_architecture() is False


def test_ordinary_x64_windows_is_left_alone(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)

    assert use_process_architecture() is False


def test_matching_values_are_left_alone(monkeypatch):
    """WOW64 でも両方 AMD64 なら食い違っていないので何もしない。"""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "AMD64")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "amd64")

    assert use_process_architecture() is False
