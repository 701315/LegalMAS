# tests/unit/services/test_dd_request_composer.py

"""
Unit tests for dd_request_composer.compose_dd_request.

Priority chain:
  1. Explicit YAML dd_request_templates[check_id] — manual text wins.
  2. Auto by review_status via t_export.
  3. Fallback loader.render().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.dd_request_composer import compose_dd_request


def _make_loader(
    explicit: dict | None = None,
    rendered: tuple[str, str] = ("fallback text", "fallback addr"),
):
    loader = MagicMock()
    loader.get_explicit_template.return_value = explicit
    loader.format_doc_names.return_value = '"doc.pdf"'
    loader.render.return_value = rendered
    return loader


def _make_check_def(check_id: str = "chk_1", name: str = "Check Name"):
    cd = MagicMock()
    cd.id = check_id
    cd.name = name
    return cd


# ═══════════════════════════════════════════════════════════════════════════
# Priority 1 — explicit YAML wins
# ═══════════════════════════════════════════════════════════════════════════

class TestExplicitYAMLWins:
    def test_explicit_template_takes_priority(self):
        loader = _make_loader(explicit={
            "text": "Manual: {check_name} in {doc_names}",
            "addressee": "Legal Counsel",
        })
        cr = {"check_id": "chk_1", "review_status": "clause_missing"}
        text, addr = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(),
            doc_names=["doc.pdf"],
            loader=loader,
            locale="ru",
        )
        assert text == 'Manual: Check Name in "doc.pdf"'
        assert addr == "Legal Counsel"
        loader.render.assert_not_called()

    def test_explicit_without_addressee_uses_default(self):
        loader = _make_loader(explicit={"text": "Manual: {check_name}"})
        cr = {"check_id": "chk_1"}
        _, addr = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(),
            doc_names=[],
            loader=loader,
            locale="ru",
        )
        assert addr  # не пустой


# ═══════════════════════════════════════════════════════════════════════════
# Priority 2 — auto by review_status
# ═══════════════════════════════════════════════════════════════════════════

class TestAutoByReviewStatus:
    @pytest.mark.parametrize(
        "rs",
        ["clause_missing", "clause_partially_defined", "unclear"],
    )
    def test_auto_status_renders_via_t_export(self, rs: str):
        loader = _make_loader(explicit=None)
        cr = {"check_id": "chk_1", "review_status": rs}

        with patch("services.dd_request_composer.t_export") as mock_t:
            mock_t.side_effect = [
                f"Auto text for {rs}",  # text
                "Auto addressee",        # addressee
            ]
            text, addr = compose_dd_request(
                check_result=cr,
                check_def=_make_check_def(),
                doc_names=["doc.pdf"],
                loader=loader,
                locale="ru",
            )

        assert text == f"Auto text for {rs}"
        assert addr == "Auto addressee"
        keys = [c.args[0] for c in mock_t.call_args_list]
        assert f"dd_request.{rs}.text" in keys
        assert f"dd_request.{rs}.addressee" in keys
        loader.render.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Priority 3 — fallback
# ═══════════════════════════════════════════════════════════════════════════

class TestFallbackToRender:
    def test_clause_defined_falls_back_to_render(self):
        loader = _make_loader(
            explicit=None,
            rendered=("Fallback text", "Fallback addr"),
        )
        cr = {"check_id": "chk_1", "review_status": "clause_defined"}
        text, addr = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(),
            doc_names=["doc.pdf"],
            loader=loader,
            locale="ru",
        )
        assert text == "Fallback text"
        assert addr == "Fallback addr"
        loader.render.assert_called_once()

    def test_missing_review_status_falls_back(self):
        loader = _make_loader(
            explicit=None,
            rendered=("Fallback text", "Fallback addr"),
        )
        cr = {"check_id": "chk_1"}  # без review_status
        text, _ = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(),
            doc_names=["doc.pdf"],
            loader=loader,
            locale="ru",
        )
        assert text == "Fallback text"
        loader.render.assert_called_once()

    def test_t_export_returns_key_falls_back(self):
        """t_export без перевода возвращает сам ключ → composer падает в render()."""
        loader = _make_loader(
            explicit=None,
            rendered=("Fallback text", "Fallback addr"),
        )
        cr = {"check_id": "chk_1", "review_status": "clause_missing"}

        with patch("services.dd_request_composer.t_export") as mock_t:
            mock_t.side_effect = lambda key, *a, **kw: key
            text, _ = compose_dd_request(
                check_result=cr,
                check_def=_make_check_def(),
                doc_names=["doc.pdf"],
                loader=loader,
                locale="ru",
            )
        assert text == "Fallback text"
        loader.render.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases — check_name resolution
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckNameResolution:
    def test_check_name_from_result_wins(self):
        loader = _make_loader(explicit={"text": "{check_name}"})
        cr = {"check_id": "chk_1", "check_name": "Localized Name"}
        text, _ = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(name="Canonical"),
            doc_names=[],
            loader=loader,
            locale="ru",
        )
        assert text == "Localized Name"

    def test_check_name_falls_back_to_check_def_name(self):
        loader = _make_loader(explicit={"text": "{check_name}"})
        cr = {"check_id": "chk_1"}
        text, _ = compose_dd_request(
            check_result=cr,
            check_def=_make_check_def(name="Canonical"),
            doc_names=[],
            loader=loader,
            locale="ru",
        )
        assert text == "Canonical"

    def test_check_name_falls_back_to_check_id(self):
        loader = _make_loader(explicit={"text": "{check_name}"})
        cr = {"check_id": "chk_1"}
        cd = _make_check_def()
        cd.name = None
        cd.id = "chk_1"
        text, _ = compose_dd_request(
            check_result=cr,
            check_def=cd,
            doc_names=[],
            loader=loader,
            locale="ru",
        )
        assert text == "chk_1"
