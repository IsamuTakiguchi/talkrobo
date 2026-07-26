"""子供のプロフィール（名前・おぼえていること）と、会話の短期履歴。

長期記憶の抽出は会話中には行わず、セッション終了後に1回だけ実行する
（会話中のレイテンシに影響させないため）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import Config
from .client import ChatClient

log = logging.getLogger(__name__)

MAX_FACTS = 30


class ChildProfile(BaseModel):
    display: str = ""  # 呼びかけに使う表記（ひらがな推奨）
    reading: str = ""  # TTS に渡すかな読み
    honorific: str = "くん"  # くん / ちゃん / ""
    age: int = 6

    @property
    def call_name(self) -> str:
        return f"{self.display}{self.honorific}"

    @property
    def spoken_name(self) -> str:
        return f"{self.reading or self.display}{self.honorific}"


class Profile(BaseModel):
    child: ChildProfile = Field(default_factory=ChildProfile)
    facts: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def load(cls, path: Path) -> Profile | None:
        if not path.exists():
            return None
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("profile.json の読み込みに失敗しました: %s", path)
            return None

    def save(self, path: Path) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def add_facts(self, facts: list[str]) -> int:
        """重複を避けて追記する。追加できた件数を返す。"""
        added = 0
        existing = {f.strip() for f in self.facts}
        for fact in facts:
            fact = fact.strip()
            if fact and fact not in existing:
                self.facts.append(fact)
                existing.add(fact)
                added += 1
        # 増えすぎたら古いものから捨てる
        if len(self.facts) > MAX_FACTS:
            self.facts = self.facts[-MAX_FACTS:]
        return added


def load_or_build_profile(config: Config) -> tuple[Profile, bool]:
    """プロフィールを解決する。

    返り値は (profile, 名前のオンボーディングが必要か)。

    解決順:
      1. data/profile.json があればそれを使う
      2. config.yaml の child.name があればそれを使い、profile.json に書き出す
      3. どちらも無ければオンボーディングが必要
    """
    profile = Profile.load(config.profile_path)
    if profile and profile.child.display.strip():
        return profile, False

    profile = profile or Profile()

    if config.child.is_configured:
        profile.child = ChildProfile(
            display=config.child.name.strip(),
            reading=config.child.reading.strip(),
            honorific=config.child.honorific.strip(),
            age=config.child.age,
        )
        profile.save(config.profile_path)
        return profile, False

    profile.child.age = config.child.age
    profile.child.honorific = config.child.honorific.strip()
    return profile, True


# ---------------------------------------------------------------------------
# 短期履歴
# ---------------------------------------------------------------------------


class History:
    """Claude に送る直近の会話。古いものから切り捨てて入力コストを抑える。"""

    def __init__(self, max_turns: int = 8) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_messages = max_turns * 2

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, text: str) -> None:
        if not text.strip():
            return
        self._messages.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self) -> None:
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages :]
        # 先頭は必ず user から始める必要がある
        while self._messages and self._messages[0]["role"] != "user":
            self._messages.pop(0)

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    @property
    def is_empty(self) -> bool:
        return not self._messages

    def transcript(self) -> str:
        role_label = {"user": "子供", "assistant": "ロボット"}
        return "\n".join(
            f"{role_label.get(m['role'], m['role'])}: {m['content']}" for m in self._messages
        )


# ---------------------------------------------------------------------------
# セッション終了後の記憶抽出
# ---------------------------------------------------------------------------

_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "次回の会話で役立つ、子供についての短い事実",
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

_FACT_SYSTEM = """\
あなたは子供向け会話ロボットの記憶係です。
会話ログから「次回このロボットが子供と話すときに覚えておくと嬉しい事実」を抜き出します。

ルール:
- 1件は20文字以内の短い日本語で書く（例: 「きょうりゅうがすき」「いもうとの名前はさくら」）
- 好きなもの・苦手なもの・家族やペット・習い事・最近の出来事 を優先する
- 住所・電話番号・学校名など、特定につながる個人情報は書かない
- 一時的なこと（今日の天気など）は書かない
- 該当が無ければ空の配列を返す
- 最大5件まで
"""


def extract_facts(client: ChatClient, history: History) -> list[str]:
    """会話ログから覚えておくべき事実を抽出する（セッション終了後に1回だけ呼ぶ）。"""
    if history.is_empty:
        return []
    result = client.complete_json(
        system=_FACT_SYSTEM,
        user=f"会話ログ:\n{history.transcript()}",
        schema=_FACT_SCHEMA,
        max_tokens=300,
    )
    if not result:
        return []
    facts = result.get("facts")
    if not isinstance(facts, list):
        return []
    return [str(f) for f in facts if isinstance(f, str | int | float)][:5]


def save_session_memory(
    config: Config, client: ChatClient, profile: Profile, history: History
) -> int:
    """会話から事実を抽出して profile.json に保存する。追加件数を返す。"""
    try:
        facts = extract_facts(client, history)
    except Exception:
        log.exception("記憶の抽出に失敗しました")
        return 0
    if not facts:
        return 0
    added = profile.add_facts(facts)
    if added:
        profile.save(config.profile_path)
    return added


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
