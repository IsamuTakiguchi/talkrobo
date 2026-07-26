"""からだ（見た目・動き）のインターフェース。

PC 開発では `MockBody`、Raspberry Pi では `PiBody` が入る。
app.py はどちらが入っているかを知らない。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..states import Emotion, RobotState


@runtime_checkable
class Body(Protocol):
    """しっぽ・首・目・ほっぺ をまとめて扱う。

    実装は必ず非ブロッキングであること（会話ループを止めない）。
    """

    def set_state(self, state: RobotState) -> None:
        """会話の状態が変わったときに呼ばれる。聴取中/考え中 の表現を切り替える。"""

    def set_emotion(self, emotion: Emotion) -> None:
        """LLM が返した感情。目とほっぺの色、しっぽ、首に反映する。"""

    def close(self) -> None:
        """後始末（サーボを中立に戻す、LED を消す）。"""


class NullBody:
    """何もしないからだ。テストや `--no-body` 用。"""

    def set_state(self, state: RobotState) -> None:  # noqa: D102
        pass

    def set_emotion(self, emotion: Emotion) -> None:  # noqa: D102
        pass

    def close(self) -> None:  # noqa: D102
        pass
