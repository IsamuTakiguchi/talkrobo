"""相づち（間つなぎ）のテスト。実際の音は鳴らさない。"""

from __future__ import annotations

import random
import time

from conftest import FakeVoice

from talkrobo.audio.filler import FillerPlayer
from talkrobo.config import FillerConfig


def fast_config(**overrides) -> FillerConfig:
    base = {
        "enabled": True,
        "ack_after": 0.02,
        "thinking_after": 0.05,
        "wait_after": 0.08,
        "timeout_after": 0.11,
    }
    base.update(overrides)
    return FillerConfig(**base)


def test_ack_comes_first(persona):
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config())
    filler.start()
    time.sleep(0.04)
    filler.stop()

    assert len(voice.said) == 1
    assert voice.said[0] in persona.fillers["ack"]


def test_all_stages_run_in_order(persona):
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config())
    filler.start()
    time.sleep(0.2)
    filler.stop()

    assert voice.said[0] in persona.fillers["ack"]
    assert voice.said[1] in persona.fillers["thinking"]
    assert voice.said[2] in persona.fillers["wait"]
    assert voice.said[3] in persona.fillers["timeout"]
    assert filler.timed_out()


def test_stop_prevents_further_fillers(persona):
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config())
    filler.start()
    time.sleep(0.04)
    filler.stop()
    said_at_stop = len(voice.said)

    time.sleep(0.15)
    assert len(voice.said) == said_at_stop
    assert not filler.timed_out()


def test_disabled_filler_says_nothing(persona):
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config(enabled=False))
    filler.start()
    time.sleep(0.15)
    filler.stop()

    assert voice.said == []


def test_skipped_while_voice_is_busy(persona):
    """前の相づちがまだ鳴っているときは重ねない。"""

    class BusyVoice(FakeVoice):
        def is_busy(self) -> bool:
            return True

    voice = BusyVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config())
    filler.start()
    time.sleep(0.15)
    filler.stop()

    assert voice.said == []


def test_same_filler_is_not_repeated_consecutively(persona):
    """同じ相づちを連呼すると機械っぽく聞こえるので避ける。"""
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config(), rng=random.Random(0))
    picks = [filler._pick("ack") for _ in range(6)]

    assert len(persona.fillers["ack"]) > 1
    for previous, current in zip(picks, picks[1:], strict=False):
        assert previous != current


def test_restart_resets_timeout_flag(persona):
    voice = FakeVoice()
    filler = FillerPlayer(persona=persona, voice=voice, config=fast_config())
    filler.start()
    time.sleep(0.2)
    assert filler.timed_out()

    filler.start()
    assert not filler.timed_out()
    filler.stop()
