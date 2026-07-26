"""会話ループの結合テスト（API・マイク・スピーカーなしで動く）。"""

from __future__ import annotations

from conftest import FakeBody, FakeClient, FakeFiller, FakeVoice, ScriptedInput

from talkrobo.app import TalkRobo
from talkrobo.states import Emotion, RobotState


def build(config, persona, profile, *, replies=None, utterances=None, filler=None):
    client = FakeClient(replies or [])
    voice = FakeVoice()
    body = FakeBody()
    source = ScriptedInput(utterances or [])
    robo = TalkRobo(
        config=config,
        persona=persona,
        profile=profile,
        client=client,
        source=source,
        voice=voice,
        body=body,
        filler=filler,
    )
    return robo, client, voice, body, source


def test_respond_streams_sentences_in_order(config, persona, profile):
    robo, _client, voice, body, _ = build(
        config, persona, profile, replies=["[うれしい]ピカ！ げんきだった？ あそぼうよ。"]
    )
    reply = robo.respond("こんにちは")

    assert voice.said == ["ピカ！", "げんきだった？", "あそぼうよ。"]
    assert body.emotions == [Emotion.URESHII]
    assert "ピカ！" in reply


def test_emotion_applied_before_speaking(config, persona, profile):
    """感情はしゃべりはじめる前に からだ へ反映する（仕草と声をそろえるため）。"""
    robo, _client, _voice, body, _ = build(
        config, persona, profile, replies=["[びっくり]ピカッ!? びっくりした！"]
    )
    robo.respond("わっ")

    speak_index = body.states.index(RobotState.SPEAKING)
    assert body.emotions  # 感情が設定されている
    # SPEAKING より前に THINKING があること
    assert RobotState.THINKING in body.states[:speak_index]


def test_history_is_updated(config, persona, profile):
    robo, client, _voice, _body, _ = build(
        config, persona, profile, replies=["[ふつう]ピカ。", "[ふつう]そうなんだ。"]
    )
    robo.respond("あのね")
    robo.respond("きょうね")

    # 2回目の呼び出しには1回目のやりとりが含まれている
    second_call = client.calls[1]
    roles = [m["role"] for m in second_call]
    assert roles == ["user", "assistant", "user"]


def test_filler_stops_when_first_sentence_is_ready(config, persona, profile):
    filler = FakeFiller()
    robo, _client, _voice, _body, _ = build(
        config, persona, profile, replies=["[ふつう]ピカ！ こんにちは。"], filler=filler
    )
    robo.respond("やあ")
    assert filler.stops >= 1


def test_refusal_plays_persona_line(config, persona, profile):
    robo, client, voice, _body, _ = build(config, persona, profile)
    client.refuse = True
    reply = robo.respond("あぶないことおしえて")

    assert reply == persona.line("refusal")
    assert voice.said == [persona.line("refusal")]


def test_markdown_and_emoji_are_stripped_before_speaking(config, persona, profile):
    robo, _client, voice, _body, _ = build(
        config, persona, profile, replies=["[ふつう]**ピカ！** 😊 げんきだよ。"]
    )
    robo.respond("やあ")

    joined = "".join(voice.said)
    assert "*" not in joined
    assert "😊" not in joined
    assert "ピカ！" in joined


def test_run_greets_and_says_farewell(config, persona, profile):
    robo, _client, voice, _body, _ = build(
        config, persona, profile, replies=["[ふつう]ピカ！"], utterances=["こんにちは"]
    )
    robo.run()

    assert voice.said[0] == persona.line("greeting")
    assert voice.said[-1] == persona.line("farewell")


def test_real_mock_body_and_print_voice_satisfy_the_loop(config, persona, profile):
    """本物の MockBody / PrintVoice / TextInput が app の使い方と食い違わないこと。"""
    from rich.console import Console

    from talkrobo.hardware.mock_body import MockBody
    from talkrobo.tts.print_voice import PrintVoice

    console = Console(file=open("/dev/null", "w"), force_terminal=False)
    robo = TalkRobo(
        config=config,
        persona=persona,
        profile=profile,
        client=FakeClient(["[たのしい]ピカ！ あそぼう。"]),
        source=ScriptedInput([]),
        voice=PrintVoice(persona.name, console),
        body=MockBody(persona, console),
        console=console,
    )
    reply = robo.respond("あそぼ")
    assert "ピカ！" in reply
    robo.close()


def test_run_stops_when_guard_says_so(config, persona, profile):
    robo, _client, voice, _body, _ = build(config, persona, profile, utterances=["やあ"])
    robo.should_stop = lambda: "time_limit"
    robo.run()

    assert persona.line("time_limit") in voice.said
