"""VOICEVOX ENGINE を使った日本語音声合成。

    docker run -d -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest

※ VOICEVOX は音声ライブラリごとに利用規約が異なり、クレジット表記が必要です。
   使用する話者の規約を必ず確認してください。
"""

from __future__ import annotations

import hashlib
import io
import logging
import queue
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import numpy as np
import soundfile as sf

from ..persona import PersonaVoice

if TYPE_CHECKING:  # 再生側は sounddevice に依存するので、型のときだけ読み込む
    from ..audio.player import AudioPlayer

log = logging.getLogger(__name__)


class VoicevoxError(RuntimeError):
    pass


class VoicevoxClient:
    """VOICEVOX ENGINE への同期 HTTP クライアント。"""

    def __init__(self, url: str, voice: PersonaVoice, timeout: float = 20.0) -> None:
        self._url = url.rstrip("/")
        self._voice = voice
        self._client = httpx.Client(timeout=timeout)

    def check(self) -> str:
        """起動しているか確認する。バージョン文字列を返す。"""
        try:
            response = self._client.get(f"{self._url}/version")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise VoicevoxError(
                f"VOICEVOX ENGINE に接続できません ({self._url})。\n"
                "  docker run -d -p 50021:50021 "
                "voicevox/voicevox_engine:cpu-ubuntu20.04-latest\n"
                "で起動してから、もう一度お試しください。"
            ) from exc
        return response.text.strip().strip('"')

    def synth(self, text: str) -> bytes:
        """テキストを WAV バイト列にする。"""
        speaker = self._voice.speaker_id
        query = self._client.post(
            f"{self._url}/audio_query", params={"text": text, "speaker": speaker}
        )
        query.raise_for_status()
        payload = query.json()
        payload["speedScale"] = self._voice.speed
        payload["pitchScale"] = self._voice.pitch
        payload["intonationScale"] = self._voice.intonation

        audio = self._client.post(
            f"{self._url}/synthesis", params={"speaker": speaker}, json=payload
        )
        audio.raise_for_status()
        return audio.content

    def voice_key(self) -> str:
        """声の設定を表すハッシュ（キャッシュの鍵に使う）。"""
        raw = (
            f"{self._voice.speaker_id}:{self._voice.speed}:"
            f"{self._voice.pitch}:{self._voice.intonation}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:8]

    def close(self) -> None:
        self._client.close()


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    samples, samplerate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    return samples, samplerate


class VoicevoxVoice:
    """合成と再生をパイプライン化した Voice 実装。

    `say()` は合成キューに積むだけで即座に返る。合成スレッドが WAV を作り、
    プレイヤーのキューへ渡す。文が確定するたびに積んでいけば、
    1文目を鳴らしている間に2文目の合成が進む。
    """

    def __init__(
        self,
        client: VoicevoxClient,
        player: AudioPlayer,
    ) -> None:
        self._client = client
        self._player = player
        self._queue: queue.Queue[tuple[str, Path | None] | None] = queue.Queue()
        self._lock = threading.Condition()
        self._pending = 0
        self._closed = False
        self._thread = threading.Thread(target=self._worker, name="voicevox-synth", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def say(self, text: str, *, cached_wav: Path | None = None) -> None:
        text = text.strip()
        if not text or self._closed:
            return
        with self._lock:
            self._pending += 1
        self._queue.put((text, cached_wav))

    def is_busy(self) -> bool:
        with self._lock:
            if self._pending > 0:
                return True
        return self._player.is_busy()

    def wait_until_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            self._lock.wait_for(lambda: self._pending == 0, timeout=timeout)
        self._player.wait_until_idle(timeout=timeout)

    def stop(self) -> None:
        drained = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                drained += 1
            self._queue.task_done()
        with self._lock:
            self._pending = max(0, self._pending - drained)
            self._lock.notify_all()
        self._player.stop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=3.0)
        self._player.close()
        self._client.close()

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            text, cached = item
            try:
                if cached and cached.exists():
                    samples, samplerate = decode_wav(cached.read_bytes())
                else:
                    samples, samplerate = decode_wav(self._client.synth(text))
                self._player.play(samples, samplerate)
            except Exception:
                log.exception("音声合成に失敗しました: %r", text)
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - 1)
                    self._lock.notify_all()
                self._queue.task_done()


def build_wav_cache(
    client: VoicevoxClient,
    texts: list[str],
    cache_dir: Path,
    persona_hash: str,
    *,
    on_progress=None,
) -> dict[str, Path]:
    """相づちや決まり文句を先に合成してファイルに置く。

    相づちを都度合成していては「間」に間に合わないので、起動時にまとめて作る。
    ペルソナや声の設定が変わるとハッシュが変わり、自動的に作り直される。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    voice_key = client.voice_key()
    result: dict[str, Path] = {}

    for index, text in enumerate(texts):
        digest = hashlib.sha256(f"{persona_hash}:{voice_key}:{text}".encode()).hexdigest()[:16]
        path = cache_dir / f"{digest}.wav"
        if not path.exists():
            if on_progress:
                on_progress(index + 1, len(texts), text)
            try:
                path.write_bytes(client.synth(text))
            except Exception:
                log.exception("相づちの事前合成に失敗しました: %r", text)
                continue
        result[text] = path
    return result
