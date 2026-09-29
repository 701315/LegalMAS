"""
B7.9.2 — primary anchor → check-level denormalization sync.

Проверяет:
- EXACT_SPAN + ui_mode=field_extraction → cr.page/clause_uid/element_id/bbox
  синхронизируются из primary_row.
- FUZZY_SPAN conf >= 0.5 → синхронизируется.
- FUZZY_SPAN conf < 0.5 → не синхронизируется.
- CLAUSE_ONLY / PAGE_ONLY / LAYOUT_ONLY / RETRIEVAL_LEGACY → не синхронизируется.
- ui_mode != "field_extraction" → не синхронизируется.
- None-значения в primary_row не перетирают существующие cr.* значения.
- bbox собирается в канонический dict {union, page, element_ids}.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.anchors.models import CheckAnchor
from db.repositories.result_repo import ResultRepository


def _a(method: str, conf: float = 1.0, quote: str = "q") -> CheckAnchor:
    kwargs: dict = {
        "anchor_method": method,
        "anchor_confidence": conf,
        "quoted_text": quote,
    }
    if method in ("exact_span", "fuzzy_span"):
        kwargs["span_start"] = 0
        kwargs["span_end"] = len(quote)
    return CheckAnchor(**kwargs)


def _mock_cr(ui_mode: str = "field_extraction", **overrides) -> MagicMock:
    cr = MagicMock()
    cr.id = uuid.uuid4()
    cr.ui_mode = ui_mode
    cr.page = 1
    cr.clause_uid = "main_contract:R15"
    cr.element_id = "el-R15"
    cr.bbox = {"union": [0.0, 0.0, 0.0, 0.0], "page": 1, "element_ids": ["el-R15"]}
    cr.primary_anchor_id = None
    cr.primary_anchor_method = None
    cr.primary_anchor_confidence = None
    cr.anchor_stale = True
    for k, v in overrides.items():
        setattr(cr, k, v)
    return cr


_UNSET = object()


def _mock_anchor_row(
    *,
    page: int | None = 4,
    clause_uid: str | None = "main_contract:7.2",
    layout_element_ids: list | None = _UNSET,
    bbox_union: list | None = _UNSET,
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.page = page
    row.clause_uid = clause_uid
    row.layout_element_ids = (
        ["el-a", "el-b"] if layout_element_ids is _UNSET else layout_element_ids
    )
    row.bbox_union = (
        [10.0, 20.0, 30.0, 40.0] if bbox_union is _UNSET else bbox_union
    )
    return row


async def _run_replace(cr, anchors, anchor_row):
    session = AsyncMock()
    repo = ResultRepository(session)
    anchor_repo = AsyncMock()
    anchor_repo.replace_for_check_result = AsyncMock(return_value=[anchor_row])
    anchor_repo.set_primary = AsyncMock(return_value=anchor_row)
    with patch(
        "db.repositories.result_repo.CheckResultAnchorRepository",
        return_value=anchor_repo,
    ):
        await repo._replace_anchors_for_check_result(cr=cr, anchors=anchors)
    return cr


@pytest.mark.asyncio
async def test_exact_span_field_extraction_syncs_all_columns():
    cr = _mock_cr(ui_mode="field_extraction")
    row = _mock_anchor_row()
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.page == 4
    assert cr.clause_uid == "main_contract:7.2"
    assert cr.element_id == "el-a"
    assert cr.bbox == {
        "union": [10.0, 20.0, 30.0, 40.0],
        "page": 4,
        "element_ids": ["el-a", "el-b"],
    }


@pytest.mark.asyncio
async def test_fuzzy_span_high_confidence_syncs():
    cr = _mock_cr()
    row = _mock_anchor_row()
    await _run_replace(cr, [_a("fuzzy_span", 0.8, quote="fuzzy")], row)

    assert cr.page == 4
    assert cr.clause_uid == "main_contract:7.2"
    assert cr.element_id == "el-a"


@pytest.mark.asyncio
async def test_fuzzy_span_low_confidence_does_not_sync():
    cr = _mock_cr()
    row = _mock_anchor_row()
    await _run_replace(cr, [_a("fuzzy_span", 0.4, quote="weak")], row)

    assert cr.page == 1
    assert cr.clause_uid == "main_contract:R15"
    assert cr.element_id == "el-R15"


@pytest.mark.parametrize(
    "method,conf",
    [
        ("clause_only", 0.5),
        ("page_only", 0.3),
        ("layout_only", 0.4),
        ("retrieval_legacy", 0.2),
    ],
)
@pytest.mark.asyncio
async def test_weak_methods_do_not_sync(method, conf):
    cr = _mock_cr()
    row = _mock_anchor_row()
    await _run_replace(cr, [_a(method, conf, quote="x")], row)

    assert cr.page == 1
    assert cr.clause_uid == "main_contract:R15"
    assert cr.element_id == "el-R15"


@pytest.mark.asyncio
async def test_non_field_extraction_ui_mode_does_not_sync():
    cr = _mock_cr(ui_mode="risk_detection")
    row = _mock_anchor_row()
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.page == 1
    assert cr.clause_uid == "main_contract:R15"
    assert cr.element_id == "el-R15"


@pytest.mark.asyncio
async def test_ui_mode_none_does_not_sync():
    cr = _mock_cr(ui_mode=None)
    row = _mock_anchor_row()
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.page == 1
    assert cr.clause_uid == "main_contract:R15"


@pytest.mark.asyncio
async def test_page_none_does_not_overwrite_existing_page():
    cr = _mock_cr()
    row = _mock_anchor_row(page=None)
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.page == 1
    assert cr.clause_uid == "main_contract:7.2"


@pytest.mark.asyncio
async def test_clause_uid_none_does_not_overwrite_existing_clause_uid():
    cr = _mock_cr()
    row = _mock_anchor_row(clause_uid=None)
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.page == 4
    assert cr.clause_uid == "main_contract:R15"


@pytest.mark.asyncio
async def test_empty_layout_element_ids_does_not_overwrite_element_id():
    cr = _mock_cr()
    row = _mock_anchor_row(layout_element_ids=[])
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.element_id == "el-R15"


@pytest.mark.asyncio
async def test_bbox_union_none_does_not_overwrite_bbox():
    cr = _mock_cr()
    original_bbox = cr.bbox
    row = _mock_anchor_row(bbox_union=None)
    await _run_replace(cr, [_a("exact_span", 1.0, quote="e")], row)

    assert cr.bbox == original_bbox


def test_is_anchor_sync_eligible_exact_span():
    assert ResultRepository._is_anchor_sync_eligible(_a("exact_span", 1.0))


def test_is_anchor_sync_eligible_fuzzy_high():
    assert ResultRepository._is_anchor_sync_eligible(_a("fuzzy_span", 0.5))


def test_is_anchor_sync_eligible_fuzzy_low():
    assert not ResultRepository._is_anchor_sync_eligible(_a("fuzzy_span", 0.49))


def test_is_anchor_sync_eligible_weak_methods():
    assert not ResultRepository._is_anchor_sync_eligible(_a("clause_only", 0.9))
    assert not ResultRepository._is_anchor_sync_eligible(_a("page_only", 0.9))
