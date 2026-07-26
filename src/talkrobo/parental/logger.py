"""会話ログ。保護者があとから読み返せるように JSONL で残す。

ログは data/logs/ にローカル保存され、外部には送信しない。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class ConversationLogger:
    def __init__(self, log_dir: Path) -> None:
        self._dir = log_dir

    def _path(self) -> Path:
        return self._dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def _write(self, record: dict[str, object]) -> None:
        record["ts"] = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with self._path().open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # ログが書けなくても会話は続ける
            log.exception("会話ログの書き込みに失敗しました")

    def user(self, text: str) -> None:
        self._write({"role": "child", "text": text})

    def robot(self, text: str, emotion: str) -> None:
        self._write({"role": "robot", "text": text, "emotion": emotion})
