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


def test_first_sentence_emits_without_waiting_for_more_input():
    """1文目は区切り文字が来た瞬間に確定する（体感レイテンシの要）。"""
    s = SentenceSplitter()
    assert s.feed("ピカ！") == ["ピカ！"]


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
    s.feed("ピカ！")
    assert s.flush() == []
    s2 = SentenceSplitter()
    s2.feed("とちゅうでおわり")
    assert s2.flush() == ["とちゅうでおわり"]


def test_newline_is_a_terminator():
    s = SentenceSplitter()
    assert s.feed("いちぎょうめ\nにぎょうめ") == ["いちぎょうめ"]
