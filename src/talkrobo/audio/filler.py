"""「間」を沈黙にしないための相づち。

子供は1秒の沈黙でも「こわれた？」と感じる。録音が終わってから本応答が
鳴りはじめるまでを、段階的な相づちで埋める。

すべて起動時に合成済みの WAV を鳴らすだけなので、再生開始は実質ゼロ秒。
本応答の1文目が積まれた時点で `stop()` が呼ばれ、新しい相づちは打たなくなる。
すでに鳴っているものは途中で切らない（ぶつ切りは不自然なため）。
"""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path

from ..config import FillerConfig
from ..persona import Persona

log = logging.getLogger(__name__)


class FillerPlayer:
    def __init__(
        self,
        *,
        persona: Persona,
        voice: object,
        config: FillerConfig,
        wav_cache: dict[str, Path] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._persona = persona
        self._voice = voice
        self._config = config
        self._cache = wav_cache or {}
        self._rng = rng or random.Random()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict[str, str] = {}
        self._timed_out = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self._config.enabled:
            return
        self.stop()
        self._stop = threading.Event()
        self._timed_out = False
        self._thread = threading.Thread(target=self._run, name="filler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            thread.join(timeout=0.2)

    def timed_out(self) -> bool:
        """待ちすぎて「もういっかい言って」まで到達したか。"""
        return self._timed_out

    # ------------------------------------------------------------------
    def _schedule(self) -> list[tuple[float, str]]:
        cfg = self._config
        return [
            (cfg.ack_after, "ack"),
            (cfg.thinking_after, "thinking"),
            (cfg.wait_after, "wait"),
            (cfg.timeout_after, "timeout"),
        ]

    def _run(self) -> None:
        waited = 0.0
        for delay, group in self._schedule():
            remaining = delay - waited
            if remaining > 0 and self._stop.wait(remaining):
                return
            waited = max(waited, delay)
            if self._stop.is_set():
                return
            self._play(group)
            if group == "timeout":
                self._timed_out = True
                return

    def _play(self, group: str) -> None:
        text = self._pick(group)
        if not text:
            return
        # 前の相づちがまだ鳴っているなら重ねない（早口で連呼すると不自然）
        try:
            if self._voice.is_busy():
                return
            self._voice.say(text, cached_wav=self._cache.get(text))
        except Exception:
            log.exception("相づちの再生に失敗しました")

    def _pick(self, group: str) -> str:
        candidates = [t for t in self._persona.fillers.get(group, []) if t.strip()]
        if not candidates:
            return ""
        if len(candidates) > 1:
            # 直前と同じものは避ける（同じ相づちの連呼は機械っぽく聞こえる）
            previous = self._last.get(group)
            candidates = [c for c in candidates if c != previous] or candidates
        choice = self._rng.choice(candidates)
        self._last[group] = choice
        return choice
