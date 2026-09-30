# tests/unit/services/test_dd_request_loader.py

"""
Unit tests for DDRequestTemplateLoader file-scoped _default.

Key invariant:
    A check_id declared in a doc-type YAML's checks_v8 inherits that
    file's dd_request_templates._default when no explicit entry exists.
    This is the file-scoped fallback introduced in c5bb2f5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.export.dd_request_loader import DDRequestTemplateLoader


# ─────────────────────────────────────────────────────────────────────────
# Fixtures: two synthetic doc-type YAMLs with distinct _default
# ─────────────────────────────────────────────────────────────────────────

YAML_A = {
    "type": "doc-type",
    "checks_v8": [
        {"id": "a_only_check"},
        {"id": "shared_check"},
    ],
    "dd_request_templates": {
        "shared_check": {
            "text": "Explicit shared template from A: {check_name} in {doc_names}",
            "addressee": "Addressee A",
        },
        "_default": {
            "text": "Alpha default for {check_name} in {doc_names}",
            "addressee": "Alpha",
        },
    },
}

YAML_B = {
    "type": "doc-type",
    "checks_v8": [
        {"id": "b_only_check"},
    ],
    "dd_request_templates": {
        "_default": {
            "text": "Beta default for {check_name} in {doc_names}",
            "addressee": "Beta",
        },
    },
}


@pytest.fixture
def loader(tmp_path: Path) -> DDRequestTemplateLoader:
    (tmp_path / "a_doc.yaml").write_text(
        yaml.safe_dump(YAML_A, allow_unicode=True), encoding="utf-8"
    )
    (tmp_path / "b_doc.yaml").write_text(
        yaml.safe_dump(YAML_B, allow_unicode=True), encoding="utf-8"
    )
    return DDRequestTemplateLoader(dirs=[tmp_path])


# ─────────────────────────────────────────────────────────────────────────
# Cache structure
# ─────────────────────────────────────────────────────────────────────────

class TestCacheStructure:
    def test_cache_has_two_maps(self, loader: DDRequestTemplateLoader) -> None:
        loader.invalidate_cache()
        cache = loader._load_cache()
        assert set(cache.keys()) == {"templates", "defaults"}

    def test_explicit_template_in_templates_map(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        cache = loader._load_cache()
        assert "shared_check" in cache["templates"]
        assert "shared_check" not in cache["defaults"]

    def test_file_scoped_defaults_for_declared_checks(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        cache = loader._load_cache()
        assert cache["defaults"]["a_only_check"]["addressee"] == "Alpha"
        assert cache["defaults"]["b_only_check"]["addressee"] == "Beta"

    def test_flat_view_excludes_file_scoped_defaults(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        flat = loader.get_all_templates()
        # Explicit YAML templates appear in flat view.
        assert "shared_check" in flat
        # File-scoped defaults (for checks declared in checks_v8 but
        # without an explicit dd_request_templates entry) live in the
        # separate "defaults" map — they must NOT leak into flat view.
        assert "a_only_check" not in flat
        assert "b_only_check" not in flat


# ─────────────────────────────────────────────────────────────────────────
# render() lookup order
# ─────────────────────────────────────────────────────────────────────────

class TestRenderLookup:
    def test_explicit_template_wins(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        text, addressee = loader.render("shared_check", "Shared", ["doc.pdf"])
        assert "Explicit shared template" in text
        assert addressee == "Addressee A"

    def test_file_scoped_default_used_when_no_explicit(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        text, addressee = loader.render("a_only_check", "A only", ["doc.pdf"])
        assert "Alpha default" in text
        assert addressee == "Alpha"

        text, addressee = loader.render("b_only_check", "B only", ["doc.pdf"])
        assert "Beta default" in text
        assert addressee == "Beta"

    def test_unknown_check_falls_back_to_builtin(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        # unknown_check is not declared in any checks_v8 → builtin locale fallback
        text, addressee = loader.render(
            "totally_unknown_check", "Unknown", ["doc.pdf"]
        )
        # builtin en._default (per current builtin_templates.json)
        assert "totally_unknown_check" in text or "Unknown" in text
        assert addressee  # not empty


# ─────────────────────────────────────────────────────────────────────────
# Render formatting
# ─────────────────────────────────────────────────────────────────────────

class TestRenderFormatting:
    def test_doc_names_quoted_and_joined(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        text, _ = loader.render("a_only_check", "A", ["x.pdf", "y.pdf"])
        assert '"x.pdf"' in text
        assert '"y.pdf"' in text

    def test_more_than_five_documents_truncated(
        self, loader: DDRequestTemplateLoader
    ) -> None:
        loader.invalidate_cache()
        docs = [f"d{i}.pdf" for i in range(8)]
        text, _ = loader.render("a_only_check", "A", docs)
        assert '"d0.pdf"' in text
        assert '"d4.pdf"' in text
        assert '"d5.pdf"' not in text
