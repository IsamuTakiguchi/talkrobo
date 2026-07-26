"""マイク録音。

終了条件は `Trigger` に委ねる（ボタンを離した / 無音が続いた）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

# これ未満の音量は「無音」とみなす（float32 の RMS）
DEFAULT_SILENCE_RMS = 0.015


class Recorder:
    def __init__(
        self,
        *,
        samplerate: int = 16000,
        max_seconds: float = 15.0,
        device: object | None = None,
        silence_rms: float = DEFAULT_SILENCE_RMS,
        block_ms: int = 50,
    ) -> None:
        self._samplerate = samplerate
        self._max_seconds = max_seconds
        self._device = device
        self._silence_rms = silence_rms
        self._block = max(1, int(samplerate * block_ms / 1000))

    def record(self, should_continue: Callable[[float, float, bool], bool]) -> np.ndarray:
        """録音して float32 のモノラル配列を返す。無音だけなら空配列。"""
        chunks: list[np.ndarray] = []
        block_sec = self._block / self._samplerate
        elapsed = 0.0
        silence = 0.0
        speech_detected = False

        try:
            with sd.InputStream(
                samplerate=self._samplerate,
                channels=1,
                dtype="float32",
                device=self._device,
                blocksize=self._block,
            ) as stream:
                while elapsed < self._max_seconds:
                    data, overflowed = stream.read(self._block)
                    if overflowed:
                        log.debug("入力バッファがあふれました")
                    block = np.asarray(data, dtype="float32").reshape(-1)
                    chunks.append(block)

                    elapsed += block_sec
                    rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
                    if rms >= self._silence_rms:
                        speech_detected = True
                        silence = 0.0
                    else:
                        silence += block_sec

                    if not should_continue(elapsed, silence, speech_detected):
                        break
        except Exception:
            log.exception("録音に失敗しました")
            return np.zeros(0, dtype="float32")

        if not speech_detected or not chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(chunks)
