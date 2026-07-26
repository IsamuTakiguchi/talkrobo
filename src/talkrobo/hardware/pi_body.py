"""Raspberry Pi の実機。しっぽ・首サーボと、目・ほっぺの NeoPixel。

会話ループを絶対にブロックしないよう、動きはすべて専用スレッドで実行する。
`set_state()` / `set_emotion()` はキューに積んで即座に返る。

配線（BCM ピン番号、config.yaml の hardware セクションで変更可）:
    button_pin     17  押しボタン（GND との間に接続。内部プルアップを使用）
    tail_servo_pin 18  しっぽサーボ  (SG90 など)
    head_servo_pin 27  首サーボ
    eye_led_pin    12  目の NeoPixel   ※ PWM が使えるピンであること
    cheek_led_pin  13  ほっぺの NeoPixel
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from typing import Any

from ..config import HardwareConfig
from ..persona import Persona
from ..states import Emotion, RobotState

log = logging.getLogger(__name__)

TICK = 0.05  # アニメーションの1コマ
TAIL_SWING = 30.0  # しっぽの振り幅（度）
OFF = (0, 0, 0)


def _rgb(value: Any, default: tuple[int, int, int] = OFF) -> tuple[int, int, int]:
    if not value or len(value) != 3:
        return default
    return tuple(max(0, min(255, int(c))) for c in value)  # type: ignore[return-value]


def _scale(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    factor = max(0.0, min(1.0, factor))
    return tuple(int(c * factor) for c in color)  # type: ignore[return-value]


class PiBody:
    def __init__(self, persona: Persona, hw: HardwareConfig) -> None:
        import board  # 実機でのみ import
        import neopixel
        from gpiozero import AngularServo

        self._persona = persona
        self._hw = hw

        self._tail = AngularServo(
            hw.tail_servo_pin,
            min_angle=-90,
            max_angle=90,
            min_pulse_width=0.0005,
            max_pulse_width=0.0025,
        )
        self._head = AngularServo(
            hw.head_servo_pin,
            min_angle=-90,
            max_angle=90,
            min_pulse_width=0.0005,
            max_pulse_width=0.0025,
        )
        self._eyes = neopixel.NeoPixel(
            getattr(board, f"D{hw.eye_led_pin}"),
            hw.eye_led_count,
            brightness=hw.led_brightness,
            auto_write=False,
        )
        self._cheeks = neopixel.NeoPixel(
            getattr(board, f"D{hw.cheek_led_pin}"),
            hw.cheek_led_count,
            brightness=hw.led_brightness,
            auto_write=False,
        )

        base = persona.emotion_style(Emotion.FUTSUU)
        self._eye_color = _rgb(base.get("eyes"), (255, 200, 0))
        self._cheek_color = _rgb(base.get("cheeks"), (255, 70, 70))
        self._sparkle = False
        self._state = RobotState.IDLE
        self._phase = 0.0

        self._commands: queue.Queue[tuple[str, Any] | None] = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._worker, name="pi-body", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # 公開 API（キューに積むだけ。呼び出し側をブロックしない）
    # ------------------------------------------------------------------
    def set_state(self, state: RobotState) -> None:
        if not self._closed:
            self._commands.put(("state", state))

    def set_emotion(self, emotion: Emotion) -> None:
        if not self._closed:
            self._commands.put(("emotion", emotion))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._commands.put(None)
        self._thread.join(timeout=2.0)
        self._safe(lambda: self._eyes.fill(OFF))
        self._safe(lambda: self._eyes.show())
        self._safe(lambda: self._cheeks.fill(OFF))
        self._safe(lambda: self._cheeks.show())
        self._safe(self._relax_servos)
        self._safe(self._tail.close)
        self._safe(self._head.close)

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            try:
                command = self._commands.get(timeout=TICK)
            except queue.Empty:
                self._animate()
                continue

            if command is None:
                self._commands.task_done()
                break
            try:
                self._apply(command)
            except Exception:
                log.exception("からだの制御に失敗しました")
            finally:
                self._commands.task_done()

    def _apply(self, command: tuple[str, Any]) -> None:
        kind, value = command
        if kind == "state":
            self._state = value
            self._phase = 0.0
            if value is RobotState.THINKING:
                # 考えていることを見た目で伝える（音より効く）
                self._move_head(20)
            elif value in (RobotState.IDLE, RobotState.LISTENING):
                self._move_head(0)
            elif value is RobotState.SLEEPING:
                self._relax_servos()
        elif kind == "emotion":
            style = self._persona.emotion_style(value)
            self._eye_color = _rgb(style.get("eyes"), self._eye_color)
            self._cheek_color = _rgb(style.get("cheeks"), self._cheek_color)
            self._sparkle = bool(style.get("sparkle"))
            self._move_head(float(style.get("head", 0) or 0))
            self._wag_tail(int(style.get("tail", 0) or 0))

    # ------------------------------------------------------------------
    def _animate(self) -> None:
        """状態に応じた常時アニメーション（まばたき・明滅）。"""
        self._phase += TICK
        if self._state is RobotState.SLEEPING:
            self._show(OFF, OFF)
            return

        if self._state is RobotState.LISTENING:
            # 青くゆっくり点滅＝「きいてるよ」
            level = 0.55 + 0.45 * math.sin(self._phase * 4.0)
            self._show(_scale((60, 140, 255), level), _scale(self._cheek_color, 0.5))
            return

        if self._state is RobotState.THINKING:
            # ゆっくりした明滅＝「かんがえてる」
            level = 0.35 + 0.35 * math.sin(self._phase * 2.2)
            self._show(_scale(self._eye_color, level), _scale(self._cheek_color, level))
            return

        if self._sparkle:
            # 放電演出。ほっぺを不規則に白く光らせる
            level = 1.0 if int(self._phase * 20) % 3 else 0.15
            self._show(self._eye_color, _scale((255, 255, 255), level))
            return

        self._show(self._eye_color, self._cheek_color)

    def _show(self, eyes: tuple[int, int, int], cheeks: tuple[int, int, int]) -> None:
        self._safe(lambda: self._eyes.fill(eyes))
        self._safe(lambda: self._eyes.show())
        self._safe(lambda: self._cheeks.fill(cheeks))
        self._safe(lambda: self._cheeks.show())

    def _move_head(self, angle: float) -> None:
        angle = max(-60.0, min(60.0, angle))
        self._safe(lambda: setattr(self._head, "angle", angle))

    def _wag_tail(self, times: int) -> None:
        if times <= 0:
            return
        for _ in range(min(times, 10)):
            self._safe(lambda: setattr(self._tail, "angle", TAIL_SWING))
            time.sleep(0.11)
            self._safe(lambda: setattr(self._tail, "angle", -TAIL_SWING))
            time.sleep(0.11)
        self._safe(lambda: setattr(self._tail, "angle", 0))

    def _relax_servos(self) -> None:
        """サーボの力を抜く（じりじり鳴り続けるのを防ぐ）。"""
        self._safe(lambda: setattr(self._tail, "angle", None))
        self._safe(lambda: setattr(self._head, "angle", None))

    @staticmethod
    def _safe(action) -> None:
        try:
            action()
        except Exception:  # pragma: no cover - 実機依存
            log.debug("ハードウェア操作に失敗しました", exc_info=True)
