"""ロボットの状態と感情の定義。"""

from __future__ import annotations

from enum import StrEnum


class RobotState(StrEnum):
    """会話ループ上の状態。`Body` はこれを見て見た目を変える。"""

    SLEEPING = "sleeping"  # おやすみ時間帯 / 電源投入直後
    IDLE = "idle"  # 待機中
    LISTENING = "listening"  # 録音中
    THINKING = "thinking"  # STT + LLM 処理中
    SPEAKING = "speaking"  # 発話中


class Emotion(StrEnum):
    """LLM が返す感情タグ。ペルソナ YAML の `emotions` のキーと一致させる。"""

    URESHII = "うれしい"
    TANOSHII = "たのしい"
    BIKKURI = "びっくり"
    KANASHII = "かなしい"
    NEMUI = "ねむい"
    KOMATTA = "こまった"
    DENKI = "でんき"
    FUTSUU = "ふつう"

    @classmethod
    def parse(cls, raw: str | None) -> Emotion:
        """未知のタグや None は `ふつう` に丸める（LLM の揺れで落ちないように）。"""
        if not raw:
            return cls.FUTSUU
        cleaned = raw.strip().strip("[]（）()　 ")
        for member in cls:
            if member.value == cleaned:
                return member
        return cls.FUTSUU
