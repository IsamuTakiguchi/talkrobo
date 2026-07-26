"""発話前の整形。

LLM は指示しても記号や絵文字をまれに出す。それがそのまま TTS に渡ると
「アスタリスク」「ハッシュ」などと読み上げられて台無しになるので、
声にする直前で落とす。安全ルール本体はシステムプロンプト側にある。
"""

from __future__ import annotations

import re

_URL = re.compile(r"https?://\S+")
_MARKDOWN_BULLET = re.compile(r"^\s*[-*+•]\s+", re.MULTILINE)
_MARKDOWN_HEADING = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_MARKDOWN_EMPHASIS = re.compile(r"[*_`~]{1,3}")
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"  # 絵文字・記号
    "\U00002600-\U000027bf"  # 装飾記号
    "\U0000fe00-\U0000fe0f"  # 異体字セレクタ
    "\U0001f000-\U0001f0ff"
    "]+",
    flags=re.UNICODE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SPACES = re.compile(r"[ \t]{2,}")


def clean_for_speech(text: str) -> str:
    """音声合成に渡す前に、読み上げると不自然になる要素を取り除く。"""
    if not text:
        return ""
    out = _CONTROL.sub("", text)
    out = _URL.sub("リンク", out)
    out = _MARKDOWN_HEADING.sub("", out)
    out = _MARKDOWN_BULLET.sub("", out)
    out = _MARKDOWN_EMPHASIS.sub("", out)
    out = _EMOJI.sub("", out)
    out = _SPACES.sub(" ", out)
    return out.strip()
