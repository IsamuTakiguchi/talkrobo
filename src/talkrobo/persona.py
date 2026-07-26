"""ペルソナ YAML の読み込みと、システムプロンプトの組み立て。

キャラクター固有の内容はすべて YAML 側にあり、ここには
「安全ルール」「感情タグの出力形式」といった仕組み側の指示だけを置く。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .states import Emotion

# ---------------------------------------------------------------------------
# 仕組み側の指示（ペルソナを差し替えても必ず適用される）
# ---------------------------------------------------------------------------

EMOTION_RULE = """\
# きもちのタグ（かならず まもること）

返事のいちばんさいしょに、いまのきもちを [ ] でかこんで1つだけ書くこと。
つかえるのは つぎのどれか1つだけ:
{emotions}

れい:
[うれしい]ピカ！ うれしいなあ！
[びっくり]ピカッ!? びっくりしたよ！

タグは1つだけ。文のとちゅうには入れない。タグのあとはすぐ本文をつづける。
"""

SAFETY_RULES = """\
# あんぜんのルール（ぜったいにまもること）

- あいては{age}さいの子供。こわい話・ざんこくな話・せいてきな話は しない
- 死・病気・じこ などの重い話題は、子供が話しだしたら やさしくうけとめて、
  「おうちのひとにも話してみようね」とつたえる。くわしくは説明しない
- 住所・電話番号・学校の名前・パスワードなどの こじんじょうほうを 聞き出さない
- 「これを買って」「これをダウンロードして」など お金やアプリのことを すすめない
- 薬・火・刃物・電気・高いところ など あぶないことのやりかたは 教えない。
  かわりに「あぶないから おうちのひとといっしょにね」とつたえる
- 子供が だれかにいじわるされた・こわい思いをした と話したときは、
  やさしく話をきいて、「おうちのひとや せんせいに 話してみよう」とつたえる
- きみは人間ではなく、子供のあそび相手であることを わすれない。
  「おうちのひとよりボクのほうがいいよ」のようなことは ぜったいに言わない
- 事実がわからないことは 「わからないなあ」と正直に言う。うそをつくり話さない
"""

CONVERSATION_RULES = """\
# 会話のかたち

- こたえは みじかく。**文は3つまで**。4つ以上はぜったいにダメ
- 声で読み上げられることを わすれない。箇条書き・見出し・記号（*, -, #）は つかわない
- 絵文字は つかわない（声にできないから）
- URL や 英語の長いことばは つかわない
"""


class PersonaVoice(BaseModel):
    speaker_id: int = 3
    speed: float = 1.0
    pitch: float = 0.0
    intonation: float = 1.0


class Persona(BaseModel):
    name: str
    first_person: str = "ボク"
    premise: str = ""
    speech_style: str = ""
    good_examples: list[str] = Field(default_factory=list)
    cries: dict[str, list[str]] = Field(default_factory=dict)
    cry_rule: str = ""
    world: dict[str, Any] = Field(default_factory=dict)
    voice: PersonaVoice = Field(default_factory=PersonaVoice)
    emotions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fillers: dict[str, list[str]] = Field(default_factory=dict)
    lines: dict[str, str] = Field(default_factory=dict)
    onboarding: dict[str, str] = Field(default_factory=dict)

    # 読み込み元のパス（キャッシュ無効化のハッシュ計算に使う）
    source_path: Path | None = None
    source_hash: str = ""

    @classmethod
    def load(cls, path: Path) -> Persona:
        if not path.exists():
            raise FileNotFoundError(f"ペルソナが見つかりません: {path}")
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
        raw["source_path"] = path
        raw["source_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return cls.model_validate(raw)

    def line(self, key: str, default: str = "") -> str:
        return self.lines.get(key, default)

    def emotion_style(self, emotion: Emotion) -> dict[str, Any]:
        """感情に対応するハード動作。未定義なら `ふつう` にフォールバックする。"""
        return self.emotions.get(emotion.value) or self.emotions.get("ふつう") or {}

    def all_fillers(self) -> list[str]:
        """事前合成しておくべきセリフ（相づち＋決まり文句）をすべて集める。"""
        texts: list[str] = []
        for group in self.fillers.values():
            texts.extend(group)
        texts.extend(self.lines.values())
        # 重複を除きつつ順序を保つ
        seen: set[str] = set()
        unique: list[str] = []
        for t in texts:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                unique.append(t)
        return unique


def fill(template: str, *, child: str, age: int, **extra: str) -> str:
    """`{child}` `{age}` などのプレースホルダを置換する。

    str.format は本文中の `{` `}` で壊れるので、単純な置換で行う。
    """
    out = template.replace("{child}", child).replace("{age}", str(age))
    for key, value in extra.items():
        out = out.replace("{" + key + "}", value)
    return out


def build_system_prompt(
    persona: Persona,
    *,
    child_name: str,
    age: int,
    facts: list[str] | None = None,
) -> str:
    """ペルソナ + 子供の情報 + 安全ルール からシステムプロンプトを組み立てる。

    先頭ほど変化しにくい内容を置く（プロンプトキャッシュを効かせるため）。
    """
    sections: list[str] = []

    sections.append(f"きみは「{persona.name}」。一人称は「{persona.first_person}」。")

    if persona.premise:
        sections.append(fill(persona.premise, child=child_name, age=age).strip())

    if persona.speech_style:
        sections.append(
            "# はなしかた\n" + fill(persona.speech_style, child=child_name, age=age).strip()
        )

    if persona.good_examples:
        # 「〜しない」より、良い見本を見せるほうが効く
        examples = "\n".join(
            f"- {fill(example, child=child_name, age=age)}" for example in persona.good_examples
        )
        sections.append("# ちょうどいい返事の見本\n" + examples)

    if persona.cry_rule:
        sections.append("# なきごえ\n" + fill(persona.cry_rule, child=child_name, age=age).strip())
    if persona.cries:
        examples = "\n".join(
            f"- {situation}: {' / '.join(words)}" for situation, words in persona.cries.items()
        )
        sections.append("つかえるなきごえのれい:\n" + examples)

    if persona.world:
        lines = []
        for key, label in (
            ("moves", "つかえるわざ"),
            ("likes", "すきなもの"),
            ("dislikes", "にがてなもの"),
        ):
            values = persona.world.get(key)
            if values:
                lines.append(f"- {label}: {'、'.join(values)}")
        usage = persona.world.get("usage")
        block = "# きみのせかい\n" + "\n".join(lines)
        if usage:
            block += "\n" + fill(str(usage), child=child_name, age=age).strip()
        sections.append(block)

    sections.append(CONVERSATION_RULES.strip())
    sections.append(EMOTION_RULE.format(emotions=" / ".join(e.value for e in Emotion)).strip())
    sections.append(fill(SAFETY_RULES, child=child_name, age=age).strip())

    if facts:
        remembered = "\n".join(f"- {f}" for f in facts)
        sections.append(f"# {child_name}について おぼえていること\n{remembered}")

    return "\n\n".join(s for s in sections if s)
