"""システムプロンプトの組み立てのテスト。

ペルソナを差し替えても消えてはいけないルールが、コード側から必ず入ることを見る。
"""

from __future__ import annotations

from talkrobo.persona import Persona, build_system_prompt, fill


def build(persona: Persona, facts: list[str] | None = None) -> str:
    return build_system_prompt(persona, child_name="かのあくん", age=6, facts=facts or [])


def test_child_name_is_injected_everywhere(persona):
    prompt = build(persona)
    assert "かのあくん" in prompt
    # プレースホルダが置換されずに残っていないこと
    assert "{child}" not in prompt
    assert "{age}" not in prompt


def test_safety_rules_are_always_present(persona):
    """安全ルールはペルソナ YAML ではなくコード側にあるので、必ず入る。"""
    prompt = build(persona)
    assert "あんぜんのルール" in prompt
    assert "こじんじょうほう" in prompt


def test_rude_language_rule_is_present(persona):
    """らんぼうなことばへの対応が入っていること。"""
    prompt = build(persona)
    assert "らんぼうなことば" in prompt
    # しかりつけず、説教を繰り返さない方針であること
    assert "しかりつけない" in prompt


def test_facts_are_included_and_framed_as_things_to_use(persona):
    prompt = build(persona, facts=["ブンブンごまは ひもをねじってまわすおもちゃ"])
    assert "おぼえていること" in prompt
    assert "ブンブンごま" in prompt
    assert "つかって答える" in prompt


def test_no_facts_section_when_nothing_remembered(persona):
    assert "おぼえていること" not in build(persona)


def test_good_examples_are_included(persona):
    prompt = build(persona)
    assert "ちょうどいい返事の見本" in prompt


def test_fill_replaces_placeholders_without_breaking_braces():
    template = "{child}は{age}さい。JSON の {} はそのまま残ること"
    out = fill(template, child="かのあくん", age=6)
    assert out == "かのあくんは6さい。JSON の {} はそのまま残ること"


def test_persona_lists_every_filler_for_pre_synthesis(persona):
    """相づちと決まり文句が、事前合成の対象にすべて入ること。"""
    texts = persona.all_fillers()
    for group in persona.fillers.values():
        for line in group:
            assert line in texts
    for line in persona.lines.values():
        assert line in texts
