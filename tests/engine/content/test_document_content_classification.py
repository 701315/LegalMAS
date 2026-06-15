# tests/engine/content/test_document_content_classification.py

"""
Unit tests for _document_content_classification.py helpers.

These are pure function tests — no DB, no storage, no mocks needed.
"""

import pytest

from engine.content._document_content_classification import (
    ClassificationContentBundle,
    get_chunk_meta,
    get_chunk_kind,
    get_effective_uid,
    get_chunk_ref,
    infer_semantic_scope,
    is_preamble_chunk,
    is_main_contract_chunk,
    select_header_chunk,
    select_body_chunks,
    truncate_text,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_chunk(
    uid: str,
    kind: str,
    scope: str,
    text: str = "some content",
    chunk_id: str | None = None,
) -> dict:
    return {
        "id": chunk_id or f"doc:{kind}:{uid}",
        "text": text,
        "metadata": {
            "effective_uid": uid,
            "chunk_kind": kind,
            "scope": scope,
        },
    }


# ── infer_semantic_scope ──────────────────────────────────────────────────────


def test_infer_semantic_scope_from_uid_for_legal_unit():
    """
    AUDIT-PROVEN: for legal_unit chunks, metadata.scope contains segment_id,
    not semantic scope. Scope must be inferred from effective_uid prefix.
    """
    chunk = _make_chunk(
        uid="main_contract:1.4",
        kind="legal_unit",
        scope="e37e6543-f3e1-53f1-8bc8-72bbe9e56280",  # segment_id
    )
    assert infer_semantic_scope(chunk) == "main_contract"


def test_infer_semantic_scope_from_uid_appendix():
    chunk = _make_chunk(
        uid="appendix_1:1",
        kind="legal_unit",
        scope="some-segment-id",
    )
    assert infer_semantic_scope(chunk) == "appendix_1"


def test_infer_semantic_scope_for_section_uses_metadata():
    """
    For section chunks, metadata.scope is already semantic.
    """
    chunk = _make_chunk(
        uid="main_contract:2",
        kind="section",
        scope="main_contract",
    )
    assert infer_semantic_scope(chunk) == "main_contract"


def test_infer_semantic_scope_no_uid_fallback():
    chunk = {
        "id": "doc:section:1",
        "text": "text",
        "metadata": {
            "effective_uid": "",
            "chunk_kind": "section",
            "scope": "main_contract",
        },
    }
    assert infer_semantic_scope(chunk) == "main_contract"


# ── is_preamble_chunk ─────────────────────────────────────────────────────────


def test_is_preamble_chunk_by_uid():
    chunk = _make_chunk(
        uid="main_contract:__preamble__",
        kind="section",
        scope="main_contract",
    )
    assert is_preamble_chunk(chunk) is True


def test_is_preamble_chunk_by_id():
    chunk = {
        "id": "doc:section:main_contract:__preamble__",
        "text": "preamble text",
        "metadata": {
            "effective_uid": "",
            "chunk_kind": "section",
            "scope": "main_contract",
        },
    }
    assert is_preamble_chunk(chunk) is True


def test_not_preamble_regular_chunk():
    chunk = _make_chunk(
        uid="main_contract:1",
        kind="section",
        scope="main_contract",
    )
    assert is_preamble_chunk(chunk) is False


# ── is_main_contract_chunk ────────────────────────────────────────────────────


def test_is_main_contract_chunk_legal_unit():
    chunk = _make_chunk(
        uid="main_contract:1.4",
        kind="legal_unit",
        scope="some-segment-id",
    )
    assert is_main_contract_chunk(chunk) is True


def test_is_not_main_contract_appendix():
    chunk = _make_chunk(
        uid="appendix_1:1",
        kind="legal_unit",
        scope="some-segment-id",
    )
    assert is_main_contract_chunk(chunk) is False


# ── select_header_chunk ───────────────────────────────────────────────────────


def test_select_header_chunk_prefers_preamble():
    chunks = [
        _make_chunk("main_contract:1", "section", "main_contract", text="section 1"),
        _make_chunk("main_contract:__preamble__", "section", "main_contract", text="preamble text"),
        _make_chunk("main_contract:1.1", "legal_unit", "some-segment", text="clause"),
    ]
    result = select_header_chunk(chunks)
    assert result is not None
    assert get_effective_uid(result) == "main_contract:__preamble__"


def test_select_header_chunk_prefers_main_contract_preamble_over_appendix():
    chunks = [
        _make_chunk("appendix_1:__preamble__", "section", "appendix_1", text="appendix preamble"),
        _make_chunk("main_contract:__preamble__", "section", "main_contract", text="main preamble"),
    ]
    result = select_header_chunk(chunks)
    assert result is not None
    assert get_effective_uid(result) == "main_contract:__preamble__"


def test_select_header_chunk_returns_none_if_no_preamble():
    chunks = [
        _make_chunk("main_contract:1", "section", "main_contract", text="section"),
    ]
    result = select_header_chunk(chunks)
    assert result is None


def test_select_header_chunk_empty_list():
    assert select_header_chunk([]) is None


# ── select_body_chunks ────────────────────────────────────────────────────────


def test_select_body_excludes_preamble():
    """
    Preamble is already in header. Must not appear in body.
    """
    chunks = [
        _make_chunk("main_contract:__preamble__", "legal_unit", "some-seg", text="preamble"),
        _make_chunk("main_contract:1.1", "legal_unit", "some-seg", text="clause 1.1"),
        _make_chunk("main_contract:1.2", "legal_unit", "some-seg", text="clause 1.2"),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=5000)
    uids = [get_effective_uid(ch) for ch in selected]
    assert "main_contract:__preamble__" not in uids
    assert "main_contract:1.1" in uids
    assert "main_contract:1.2" in uids


def test_select_body_prefers_legal_unit_main_over_section_main():
    chunks = [
        _make_chunk("main_contract:1", "section", "main_contract", text="section 1"),
        _make_chunk("main_contract:1.1", "legal_unit", "some-seg", text="clause 1.1"),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=5000)
    kinds = [get_chunk_kind(ch) for ch in selected]
    assert "legal_unit" in kinds
    assert diag["body_selection_mode"] == "legal_unit_main"


def test_select_body_fallback_to_section_main():
    chunks = [
        _make_chunk("main_contract:1", "section", "main_contract", text="section 1"),
        _make_chunk("appendix_1:1", "legal_unit", "some-seg", text="appendix legal unit"),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=5000)
    assert diag["body_selection_mode"] == "section_main"
    uids = [get_effective_uid(ch) for ch in selected]
    assert "main_contract:1" in uids
    assert "appendix_1:1" not in uids


def test_select_body_fallback_to_legal_unit_other():
    """
    When no main_contract chunks available, fallback to other scopes.
    """
    chunks = [
        _make_chunk("appendix_1:1", "legal_unit", "some-seg", text="appendix content"),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=5000)
    assert diag["body_selection_mode"] == "legal_unit_fallback"
    assert len(selected) == 1


def test_select_body_empty_when_no_chunks():
    selected, diag = select_body_chunks([], max_chars=5000)
    assert selected == []
    assert diag["body_selection_mode"] == "empty"


def test_select_body_respects_max_chars():
    long_text = "word " * 1000  # 5000 chars
    chunks = [
        _make_chunk("main_contract:1.1", "legal_unit", "some-seg", text=long_text),
        _make_chunk("main_contract:1.2", "legal_unit", "some-seg", text=long_text),
        _make_chunk("main_contract:1.3", "legal_unit", "some-seg", text=long_text),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=6000)
    # After first chunk (5000 chars), budget is exceeded — second should not be included
    assert len(selected) <= 2


def test_select_body_appendix_excluded_when_main_contract_exists():
    """
    REGRESSION: appendix content must not contaminate classification body
    when main_contract content is available.

    This was the root cause of real_estate misclassification:
    appendix chunks with ЕГРН/cadastral markers entered the snippet.
    """
    chunks = [
        _make_chunk("main_contract:1.1", "legal_unit", "some-seg",
                    text="Продавец передает в собственность движимое имущество"),
        _make_chunk("appendix_1:1", "legal_unit", "some-seg",
                    text="ЕГРН кадастровый номер 78:36:0005503:4 земельный участок"),
        _make_chunk("appendix_1:2", "section", "appendix_1",
                    text="Перечень объектов недвижимости"),
    ]
    selected, diag = select_body_chunks(chunks, max_chars=5000)
    body_text = " ".join(ch["text"] for ch in selected)

    assert "ЕГРН" not in body_text, (
        "REGRESSION: appendix cadastral content must not enter classification body "
        "when main_contract content is available"
    )
    assert "движимое имущество" in body_text


# ── truncate_text ─────────────────────────────────────────────────────────────


def test_truncate_text_within_limit():
    text = "Hello world"
    assert truncate_text(text, 100) == "Hello world"


def test_truncate_text_at_word_boundary():
    text = "Hello world foo bar"
    result = truncate_text(text, 12)
    assert result is not None
    assert len(result) <= 12


def test_truncate_text_none_returns_none():
    assert truncate_text(None, 100) is None


def test_truncate_text_empty_returns_none():
    assert truncate_text("", 100) is None


def test_truncate_text_zero_limit_returns_none():
    assert truncate_text("some text", 0) is None


    