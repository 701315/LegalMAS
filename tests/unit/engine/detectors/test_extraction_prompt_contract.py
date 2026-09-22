"""
B3.1ab-fix — extraction prompt contract must mention `quote`.

Защита от регресса: если кто-то отредактирует txt-шаблоны и снова
забудет `quote`, тест упадёт.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PLAYBOOKS = REPO_ROOT / "playbooks"


def test_repo_root_resolves_to_project():
    assert (REPO_ROOT / "playbooks").is_dir(), (
        f"repo root resolution failed: {REPO_ROOT}"
    )


def test_json_format_contract_mentions_quote_in_location():
    text = (PLAYBOOKS / "json_format_ru.txt").read_text(encoding="utf-8")
    assert "quote" in text, "json_format_ru.txt must mention `quote` in location contract"
    assert text.count('"quote"') >= 2, (
        "json_format_ru.txt must reference `quote` in both location contract "
        "and hard rules (>= 2 occurrences of \"quote\")"
    )


def test_json_format_contract_requires_quote_inside_location():
    text = (PLAYBOOKS / "json_format_ru.txt").read_text(encoding="utf-8")
    lower = text.lower()
    assert "обязательн" in lower, (
        "json_format_ru.txt must explicitly require `quote` when location != null"
    )


def test_fallback_meta_mentions_quote():
    text = (PLAYBOOKS / "extraction_fallback_meta_ru.txt").read_text(encoding="utf-8")
    assert "quote" in text, "extraction_fallback_meta_ru.txt must mention `quote`"
