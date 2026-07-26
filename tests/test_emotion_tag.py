from talkrobo.llm.emotion_tag import EmotionTagExtractor
from talkrobo.states import Emotion


def drain(chunks: list[str]) -> tuple[str, Emotion]:
    ex = EmotionTagExtractor()
    out = "".join(ex.feed(c) for c in chunks)
    out += ex.flush()
    return out, ex.emotion


def test_extracts_leading_tag():
    text, emotion = drain(["[うれしい]ピカ！ げんきだよ。"])
    assert text == "ピカ！ げんきだよ。"
    assert emotion is Emotion.URESHII


def test_tag_split_across_deltas():
    text, emotion = drain(["[びっ", "くり]", "ピカッ!?"])
    assert text == "ピカッ!?"
    assert emotion is Emotion.BIKKURI


def test_fullwidth_brackets():
    text, emotion = drain(["［でんき］バチバチ！"])
    assert text == "バチバチ！"
    assert emotion is Emotion.DENKI


def test_no_tag_passes_through():
    text, emotion = drain(["ピカ！ タグはないよ。"])
    assert text == "ピカ！ タグはないよ。"
    assert emotion is Emotion.FUTSUU


def test_unknown_tag_falls_back_to_futsuu():
    text, emotion = drain(["[しらないきもち]ピカ！"])
    assert text == "ピカ！"
    assert emotion is Emotion.FUTSUU


def test_unclosed_bracket_is_given_up():
    """閉じ括弧が来ないまま長くなったら、タグではないと判断して本文として流す。"""
    long_text = "[" + "あ" * 40
    text, emotion = drain([long_text])
    assert text == long_text
    assert emotion is Emotion.FUTSUU


def test_leading_whitespace_before_tag():
    text, emotion = drain(["\n [たのしい] ", "あそぼう！"])
    assert text.strip() == "あそぼう！"
    assert emotion is Emotion.TANOSHII


def test_passthrough_after_resolution_is_cheap():
    ex = EmotionTagExtractor()
    ex.feed("[ねむい]")
    assert ex.resolved
    assert ex.feed("そのまま") == "そのまま"
