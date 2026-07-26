"""返事の先頭にある感情タグ `[うれしい]` を、ストリームから取り除く。

LLM への往復を増やさずに感情を得るための仕組み。
ストリームの最初の数文字だけを見てタグを判定し、以降は素通しする。
"""

from __future__ import annotations

from ..states import Emotion

_OPEN = "[［「【"
_CLOSE = {"[": "]", "［": "］", "「": "」", "【": "】"}


class EmotionTagExtractor:
    """`feed()` に生のデルタを渡すと、タグを除いた本文が返る。

    タグが確定するまでの数文字だけをバッファし、確定後はゼロコストで素通しする。
    """

    def __init__(self, max_scan: int = 24) -> None:
        self._max_scan = max_scan
        self._buffer = ""
        self._resolved = False
        self.emotion: Emotion = Emotion.FUTSUU

    @property
    def resolved(self) -> bool:
        """タグの有無が確定したか。"""
        return self._resolved

    def feed(self, chunk: str) -> str:
        if self._resolved:
            return chunk

        self._buffer += chunk
        stripped = self._buffer.lstrip()

        # まだ空白しか来ていない → 判断を保留
        if not stripped:
            return ""

        first = stripped[0]
        if first not in _OPEN:
            # タグは無かった。バッファをそのまま本文として流す
            self._resolved = True
            out, self._buffer = self._buffer, ""
            return out

        closer = _CLOSE[first]
        end = stripped.find(closer)
        if end != -1:
            self.emotion = Emotion.parse(stripped[1:end])
            self._resolved = True
            self._buffer = ""
            return stripped[end + 1 :]

        # 閉じ括弧が来ないまま長くなりすぎた → タグではないと判断して諦める
        if len(stripped) > self._max_scan:
            self._resolved = True
            out, self._buffer = self._buffer, ""
            return out

        return ""

    def flush(self) -> str:
        """ストリーム終了時に残っているバッファを吐き出す。"""
        if self._resolved:
            return ""
        self._resolved = True
        out, self._buffer = self._buffer, ""
        return out
