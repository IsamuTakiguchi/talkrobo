from talkrobo.llm.sentence_splitter import SentenceSplitter


def feed_all(splitter: SentenceSplitter, chunks: list[str]) -> list[str]:
    out: list[str] = []
    for chunk in chunks:
        out.extend(splitter.feed(chunk))
    out.extend(splitter.flush())
    return out


def test_splits_on_terminator():
    s = SentenceSplitter()
    assert feed_all(s, ["ピカ！", "こんにちは！"]) == ["ピカ！", "こんにちは！"]


def test_period_emits_without_waiting_for_more_input():
    """「。」は後ろに何も続かないので、その場で確定する（体感レイテンシの要）。"""
    s = SentenceSplitter()
    assert s.feed("げんきだよ。") == ["げんきだよ。"]


def test_exclamation_waits_one_delta_then_emits():
    """「！」は「!?」になりうるので1デルタだけ待ち、次が来たら確定する。"""
    s = SentenceSplitter()
    assert s.feed("ピカ！") == []
    assert s.feed("こ") == ["ピカ！"]


def test_combined_punctuation_survives_delta_boundaries():
    """1文字ずつ届いても「!?」の2文字目を落とさないこと。"""
    s = SentenceSplitter()
    out: list[str] = []
    for char in "ピカッ!?すごい。":
        out.extend(s.feed(char))
    out.extend(s.flush())
    assert out == ["ピカッ!?", "すごい。"]


def test_fullwidth_combined_punctuation_survives():
    s = SentenceSplitter()
    out: list[str] = []
    for char in "いちばん！？":
        out.extend(s.feed(char))
    out.extend(s.flush())
    assert out == ["いちばん！？"]


def test_terminator_split_across_deltas():
    s = SentenceSplitter()
    out = feed_all(s, ["ピ", "カ", "！", "げん", "きだ", "よ。"])
    assert out == ["ピカ！", "げんきだよ。"]


def test_consecutive_punctuation_kept_together():
    s = SentenceSplitter()
    assert s.feed("ピカッ!?あ") == ["ピカッ!?"]


def test_stray_punctuation_is_dropped():
    """デルタ境界で記号だけが残っても、それ単体では発話しない。"""
    s = SentenceSplitter()
    s.feed("ピカ！")
    assert s.feed("？") == []


def test_long_text_without_terminator_is_force_split():
    s = SentenceSplitter(first_max_chars=10, max_chars=20)
    out = s.feed("あいうえお、かきくけこさしすせそなにぬねの")
    assert out
    assert out[0] == "あいうえお、"


def test_flush_returns_remainder():
    s = SentenceSplitter()
    s.feed("げんきだよ。")
    assert s.flush() == []

    s2 = SentenceSplitter()
    s2.feed("とちゅうでおわり")
    assert s2.flush() == ["とちゅうでおわり"]


def test_flush_picks_up_a_sentence_that_was_waiting_for_punctuation():
    """「！」で終わったまま応答が終わっても、取り残されないこと。"""
    s = SentenceSplitter()
    assert s.feed("ピカ！") == []
    assert s.flush() == ["ピカ！"]


def test_newline_is_a_terminator():
    s = SentenceSplitter()
    assert s.feed("いちぎょうめ\nにぎょうめ") == ["いちぎょうめ"]
