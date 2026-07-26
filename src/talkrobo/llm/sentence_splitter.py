"""ストリームのテキストを「文」に切り出す。

全文の生成を待たずに1文目を TTS へ流すための部品。体感レイテンシに直結する。
1文目だけは短めに切って、とにかく早く喋りはじめる。

区切り文字が来たら即座に確定させる。ただし「！」「？」のように後ろに記号が
続きうる文字でバッファが終わっているときだけは、次のデルタを1つ待つ。
待たないと「ピカッ!?」が「ピカッ!」と「?」に割れて、2つ目が失われてしまう。
待ち時間はデルタ1つぶん（ストリーミング中は数ミリ秒）なので体感には影響しない。
"""

from __future__ import annotations

# 文の区切りになる文字
TERMINATORS = "。．！？!?…\n"
# 区切りの直後に続くなら同じ文に含めたい文字（連続する記号・閉じ括弧）
TRAILERS = "」』）)”\"'！？!?…。"
# これで終わっているときは、後ろに記号が続くかもしれないので1デルタだけ待つ。
# 「。」は後ろに何も続かないので待たない（最も多い終わり方なので即座に流す）
EXTENDABLE = "！？!?…"
# 強制分割するときに優先して切りたい位置
SOFT_BREAKS = "、，,・ "

_NON_SPEECH = set(TERMINATORS) | set(TRAILERS) | set(SOFT_BREAKS) | set(" \t\r\n「『（(")


def has_speech(text: str) -> bool:
    """読み上げる意味のある文字を含むか（記号だけの断片を弾く）。"""
    return any(ch not in _NON_SPEECH for ch in text)


class SentenceSplitter:
    """`feed()` にデルタを渡すと、確定した文のリストが返る。"""

    def __init__(self, first_max_chars: int = 20, max_chars: int = 60) -> None:
        self._buffer = ""
        self._first_max = first_max_chars
        self._max = max_chars
        self._emitted = 0

    @property
    def _limit(self) -> int:
        return self._first_max if self._emitted == 0 else self._max

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        out: list[str] = []
        while True:
            cut = self._find_cut()
            if cut is None:
                break
            sentence = self._buffer[:cut].strip()
            self._buffer = self._buffer[cut:].lstrip()
            if has_speech(sentence):
                self._emitted += 1
                out.append(sentence)
        return out

    def flush(self) -> list[str]:
        """ストリーム終了時に残りを1文として吐き出す。"""
        rest = self._buffer.strip()
        self._buffer = ""
        if not has_speech(rest):
            return []
        self._emitted += 1
        return [rest]

    # ------------------------------------------------------------------
    def _find_cut(self) -> int | None:
        if not self._buffer:
            return None
        cut = self._find_terminator()
        if cut is not None:
            return cut
        if len(self._buffer) > self._limit:
            return self._find_forced_cut()
        return None

    def _find_terminator(self) -> int | None:
        for i, ch in enumerate(self._buffer):
            if ch in TERMINATORS:
                # 「！？」のように記号が続く場合や閉じ括弧をまとめて含める
                j = i + 1
                while j < len(self._buffer) and self._buffer[j] in TRAILERS:
                    j += 1
                # バッファの末尾まで来ていて、まだ記号が続きうるなら1デルタだけ待つ
                # （待たないと「!?」の2文字目を取りこぼす）。
                # ストリームが終われば flush() が拾うので、取り残されることはない
                if j >= len(self._buffer) and self._buffer[-1] in EXTENDABLE:
                    return None
                return j
        return None

    def _find_forced_cut(self) -> int:
        """長すぎるときに読点などで区切る。無ければ上限で機械的に切る。"""
        window = self._buffer[: self._limit]
        for i in range(len(window) - 1, 0, -1):
            if window[i] in SOFT_BREAKS:
                return i + 1
        return self._limit
