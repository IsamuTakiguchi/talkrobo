"""ターミナル上の「からだ」。PC 開発ではこれで完結する。

実機の PiBody と同じ情報（目の色・ほっぺ・しっぽの回数・首の角度）を
文字で出すので、ハードが無くても動きの設計を確認できる。
"""

from __future__ import annotations

from rich.console import Console

from ..persona import Persona
from ..states import Emotion, RobotState

STATE_LABEL: dict[RobotState, tuple[str, str]] = {
    RobotState.SLEEPING: ("💤", "おやすみちゅう"),
    RobotState.IDLE: ("🙂", "まってるよ"),
    RobotState.LISTENING: ("👂", "きいてるよ"),
    RobotState.THINKING: ("💭", "かんがえちゅう"),
    RobotState.SPEAKING: ("💬", "おはなしちゅう"),
}

EMOTION_FACE: dict[Emotion, str] = {
    Emotion.URESHII: "😊",
    Emotion.TANOSHII: "😄",
    Emotion.BIKKURI: "😲",
    Emotion.KANASHII: "😢",
    Emotion.NEMUI: "😴",
    Emotion.KOMATTA: "😅",
    Emotion.DENKI: "⚡",
    Emotion.FUTSUU: "🙂",
}


def _hex(color: list[int] | tuple[int, int, int] | None) -> str:
    if not color or len(color) != 3:
        return "#888888"
    r, g, b = (max(0, min(255, int(c))) for c in color)
    return f"#{r:02x}{g:02x}{b:02x}"


class MockBody:
    """状態と感情をターミナルに描画するだけの Body。"""

    def __init__(self, persona: Persona, console: Console | None = None) -> None:
        self._persona = persona
        self._console = console or Console()
        self._state: RobotState | None = None

    def set_state(self, state: RobotState) -> None:
        if state == self._state:
            return
        self._state = state
        icon, label = STATE_LABEL.get(state, ("🤖", state.value))
        detail = {
            RobotState.LISTENING: "目=あお まばたき / 首をこちらへ",
            RobotState.THINKING: "目=ゆっくり明滅 / 首をかしげる / しっぽゆっくり",
            RobotState.SPEAKING: "感情の色で発光",
            RobotState.IDLE: "目=いつもの色",
            RobotState.SLEEPING: "LED 消灯 / サーボ脱力",
        }.get(state, "")
        self._console.print(f"  [dim]{icon} {label}[/dim] [dim italic]{detail}[/dim italic]")

    def set_emotion(self, emotion: Emotion) -> None:
        style = self._persona.emotion_style(emotion)
        eyes = _hex(style.get("eyes"))
        cheeks = _hex(style.get("cheeks"))
        tail = int(style.get("tail", 0) or 0)
        head = int(style.get("head", 0) or 0)
        sparkle = " [bold yellow]バチバチ⚡[/bold yellow]" if style.get("sparkle") else ""
        face = EMOTION_FACE.get(emotion, "🙂")

        head_label = "まっすぐ"
        if head > 0:
            head_label = f"右に{head}°かしげる"
        elif head < 0:
            head_label = f"左に{abs(head)}°かしげる"

        self._console.print(
            f"  [dim]{face} きもち={emotion.value}"
            f" 目=[/dim][{eyes}]■[/{eyes}][dim] ほっぺ=[/dim][{cheeks}]■[/{cheeks}]"
            f"[dim] しっぽ×{tail} 首={head_label}[/dim]{sparkle}"
        )

    def close(self) -> None:
        self._console.print("  [dim]💤 からだをやすめました[/dim]")
