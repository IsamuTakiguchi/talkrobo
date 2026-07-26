"""発話のきっかけ（録音の開始・終了条件）のテスト。"""

from __future__ import annotations

from talkrobo.hardware.trigger import (
    LEADING_GRACE_SEC,
    TRAILING_SILENCE_SEC,
    KeyboardTrigger,
    drain_pending_keys,
)


def test_drain_pending_keys_is_safe_without_a_terminal():
    """端末が無い環境（テスト実行時など）でも例外を投げないこと。"""
    drain_pending_keys()


def test_recording_continues_while_speaking():
    trigger = KeyboardTrigger()
    assert trigger.should_continue(elapsed=2.0, silence=0.0, speech_detected=True) is True


def test_recording_stops_after_trailing_silence():
    """話し終えて黙ったら止まる。"""
    trigger = KeyboardTrigger()
    silence = TRAILING_SILENCE_SEC + 0.1
    assert trigger.should_continue(elapsed=3.0, silence=silence, speech_detected=True) is False


def test_waits_a_while_before_the_child_starts_talking():
    """話し始めるまでは、無音でもすぐには打ち切らない。"""
    trigger = KeyboardTrigger()
    assert trigger.should_continue(elapsed=1.0, silence=1.0, speech_detected=False) is True


def test_gives_up_when_nothing_is_said():
    trigger = KeyboardTrigger()
    elapsed = LEADING_GRACE_SEC + 0.1
    assert trigger.should_continue(elapsed=elapsed, silence=elapsed, speech_detected=False) is False


def test_quit_word_ends_the_conversation(monkeypatch):
    trigger = KeyboardTrigger()
    monkeypatch.setattr(trigger._console, "input", lambda *_args, **_kw: "ばいばい")
    assert trigger.wait_for_start() is False


def test_plain_enter_starts_recording(monkeypatch):
    trigger = KeyboardTrigger()
    monkeypatch.setattr(trigger._console, "input", lambda *_args, **_kw: "")
    assert trigger.wait_for_start() is True


def test_eof_ends_the_conversation(monkeypatch):
    def raise_eof(*_args, **_kw):
        raise EOFError

    trigger = KeyboardTrigger()
    monkeypatch.setattr(trigger._console, "input", raise_eof)
    assert trigger.wait_for_start() is False


def test_pending_keys_are_drained_before_prompting(monkeypatch):
    """起動待ちの間に押された Enter を先に捨ててからプロンプトを出すこと。"""
    order: list[str] = []

    monkeypatch.setattr(
        "talkrobo.hardware.trigger.drain_pending_keys", lambda: order.append("drain")
    )
    trigger = KeyboardTrigger()
    monkeypatch.setattr(trigger._console, "input", lambda *_a, **_k: order.append("prompt") or "")

    trigger.wait_for_start()
    assert order == ["drain", "prompt"]
