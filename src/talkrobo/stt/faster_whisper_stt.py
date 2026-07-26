"""faster-whisper によるローカル音声認識。

ローカル実行なので API 費用はかからず、子供の声が外部に送られることもない。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class FasterWhisperSTT:
    def __init__(
        self,
        *,
        model_size: str = "small",
        compute_type: str = "int8",
        device: str = "auto",
        language: str = "ja",
    ) -> None:
        from faster_whisper import WhisperModel

        self._language = language
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: Any, *, hint: str | None = None) -> str:
        """録音データを文字にする。

        `hint` は `initial_prompt` として渡す。名前を聞く場面で「なまえは」を
        与えると、短い固有名詞が出やすくなる。
        """
        samples = np.asarray(audio, dtype="float32").reshape(-1)
        if samples.size == 0:
            return ""

        try:
            segments, _info = self._model.transcribe(
                samples,
                language=self._language,
                initial_prompt=hint,
                beam_size=1,  # 速度優先。子供の短い発話では精度差はほぼ無い
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return "".join(segment.text for segment in segments).strip()
        except Exception:
            log.exception("音声認識に失敗しました")
            return ""

    def close(self) -> None:
        self._model = None
