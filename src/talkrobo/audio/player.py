"""音声の再生キュー。

裏のスレッドで順番に鳴らす。`play()` はブロックしないので、
LLM のストリームから文が確定するたびに積んでいける。
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


@dataclass
class Clip:
    samples: np.ndarray
    samplerate: int
    on_done: Callable[[], None] | None = field(default=None)


class AudioPlayer:
    """FIFO で鳴らすだけの小さなプレイヤー。"""

    def __init__(self, device: Any = None) -> None:
        self._device = device
        self._queue: queue.Queue[Clip | None] = queue.Queue()
        self._lock = threading.Condition()
        self._pending = 0
        self._closed = False
        self._thread = threading.Thread(target=self._worker, name="audio-player", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def play(
        self, samples: np.ndarray, samplerate: int, on_done: Callable[[], None] | None = None
    ) -> None:
        if self._closed:
            return
        with self._lock:
            self._pending += 1
        self._queue.put(Clip(samples, samplerate, on_done))

    def is_busy(self) -> bool:
        with self._lock:
            return self._pending > 0

    def wait_until_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            self._lock.wait_for(lambda: self._pending == 0, timeout=timeout)

    def stop(self) -> None:
        """キューを捨てて、鳴っている音も止める。"""
        drained = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                drained += 1
            self._queue.task_done()
        try:
            sd.stop()
        except Exception:  # pragma: no cover - 環境依存
            log.debug("sd.stop() に失敗しました", exc_info=True)
        with self._lock:
            self._pending = max(0, self._pending - drained)
            self._lock.notify_all()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            clip = self._queue.get()
            if clip is None:
                self._queue.task_done()
                break
            try:
                sd.play(clip.samples, clip.samplerate, device=self._device)
                sd.wait()
            except Exception:  # pragma: no cover - 環境依存
                log.exception("音声の再生に失敗しました")
            finally:
                if clip.on_done:
                    try:
                        clip.on_done()
                    except Exception:
                        log.exception("再生後のコールバックで例外")
                with self._lock:
                    self._pending = max(0, self._pending - 1)
                    self._lock.notify_all()
                self._queue.task_done()
