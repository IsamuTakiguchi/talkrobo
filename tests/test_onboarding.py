"""名前オンボーディングのテスト（音声・API なしで動く）。"""

from __future__ import annotations

from conftest import FakeBody, FakeClient, FakeVoice, ScriptedInput

from talkrobo.llm.memory import Profile, load_or_build_profile
from talkrobo.llm.onboarding import run_onboarding


def run(config, persona, *, utterances, json_results):
    source = ScriptedInput(utterances)
    voice = FakeVoice()
    body = FakeBody()
    client = FakeClient(json_results=json_results)
    profile = run_onboarding(
        config=config,
        persona=persona,
        profile=Profile(),
        client=client,
        source=source,
        voice=voice,
        body=body,
    )
    return profile, voice, source, client


def test_happy_path_saves_name(config, persona):
    profile, voice, _source, _client = run(
        config,
        persona,
        utterances=["はるとです", "うん", "くん"],
        json_results=[{"display": "はると", "reading": "ハルト", "confidence": "high"}],
    )

    assert profile.child.display == "はると"
    assert profile.child.reading == "ハルト"
    assert profile.child.honorific == "くん"
    assert profile.child.call_name == "はるとくん"
    # 保存されているので次回は聞かれない
    reloaded, needs_onboarding = load_or_build_profile(config)
    assert reloaded.child.display == "はると"
    assert not needs_onboarding


def test_confirmation_is_spoken_with_the_reading(config, persona):
    """合成音声で読み上げて本人に確認してもらう（読み間違いを残さないため）。"""
    _profile, voice, _source, _client = run(
        config,
        persona,
        utterances=["はると", "うん", "ちゃん"],
        json_results=[{"display": "はると", "reading": "ハルト", "confidence": "high"}],
    )

    assert any("ハルト" in line for line in voice.said)


def test_chan_is_respected(config, persona):
    profile, _voice, _source, _client = run(
        config,
        persona,
        utterances=["さくら", "うん", "ちゃんがいい"],
        json_results=[{"display": "さくら", "reading": "サクラ", "confidence": "high"}],
    )
    assert profile.child.honorific == "ちゃん"
    assert profile.child.call_name == "さくらちゃん"


def test_stt_hint_is_set_while_asking_the_name(config, persona):
    _profile, _voice, source, _client = run(
        config,
        persona,
        utterances=["はると", "うん", "くん"],
        json_results=[{"display": "はると", "reading": "ハルト", "confidence": "high"}],
    )
    # 名前を聞く直前にヒントを立て、聞き終えたら外している
    assert "なまえは" in source.hints
    assert source.hints[-1] is None


def test_denial_triggers_retry(config, persona):
    profile, _voice, _source, client = run(
        config,
        persona,
        utterances=["はると", "ちがう", "さくら", "うん", "ちゃん"],
        json_results=[
            {"display": "はると", "reading": "ハルト", "confidence": "high"},
            {"display": "さくら", "reading": "サクラ", "confidence": "high"},
        ],
    )

    assert profile.child.display == "さくら"
    assert len(client.json_calls) == 2


def test_gives_up_after_three_failures(config, persona):
    """3回失敗したら「きみ」で会話を続ける（子供を待たせ続けない）。"""
    profile, voice, _source, _client = run(
        config,
        persona,
        utterances=["", "", ""],
        json_results=[],
    )

    assert profile.child.display == "きみ"
    assert profile.child.honorific == ""
    assert persona.onboarding["give_up"] in voice.said


def test_unrecognizable_name_is_retried(config, persona):
    profile, _voice, _source, _client = run(
        config,
        persona,
        utterances=["えーっと", "はると", "うん", "くん"],
        json_results=[
            {"display": "", "reading": "", "confidence": "low"},
            {"display": "はると", "reading": "ハルト", "confidence": "high"},
        ],
    )
    assert profile.child.display == "はると"
