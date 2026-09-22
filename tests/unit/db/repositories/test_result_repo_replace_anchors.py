"""
B4 — _replace_anchors_for_check_result integration test (AsyncMock session).

Проверяет:
- пустой anchors -> delete + обнуление 4 колонок
- непустой anchors -> replace + set_primary + денормализация
- лимит > 5 anchors применяется
- identity-lookup primary (а не equality)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from db.repositories.result_repo import ResultRepository

pytestmark = pytest.mark.asyncio


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


def _mock_cr() -> MagicMock:
    cr = MagicMock()
    cr.id = uuid.uuid4()
    cr.primary_anchor_id = None
    cr.primary_anchor_method = None
    cr.primary_anchor_confidence = None
    cr.anchor_stale = True  # чтобы проверить, что выставится False
    return cr


async def test_empty_anchors_clears_denorm_and_deletes():
    session = AsyncMock()
    repo = ResultRepository(session)
    cr = _mock_cr()

    anchor_repo = AsyncMock()
    anchor_repo.delete_for_check_result = AsyncMock(return_value=3)

    with patch(
        "db.repositories.result_repo.CheckResultAnchorRepository",
        return_value=anchor_repo,
    ):
        await repo._replace_anchors_for_check_result(cr=cr, anchors=[])

    anchor_repo.delete_for_check_result.assert_awaited_once_with(
        check_result_id=cr.id
    )
    anchor_repo.replace_for_check_result.assert_not_called()
    anchor_repo.set_primary.assert_not_called()
    assert cr.primary_anchor_id is None
    assert cr.primary_anchor_method is None
    assert cr.primary_anchor_confidence is None
    assert cr.anchor_stale is False


async def test_non_empty_anchors_replace_set_primary_denorm():
    session = AsyncMock()
    repo = ResultRepository(session)
    cr = _mock_cr()

    anchors = [
        _a("page_only", 0.3, quote="p"),
        _a("exact_span", 1.0, quote="e"),
    ]

    # created сохраняет порядок входного списка
    anchor_row_0 = MagicMock()
    anchor_row_0.id = uuid.uuid4()
    anchor_row_1 = MagicMock()
    anchor_row_1.id = uuid.uuid4()

    anchor_repo = AsyncMock()
    anchor_repo.replace_for_check_result = AsyncMock(
        return_value=[anchor_row_0, anchor_row_1]
    )
    anchor_repo.set_primary = AsyncMock(return_value=anchor_row_1)

    with patch(
        "db.repositories.result_repo.CheckResultAnchorRepository",
        return_value=anchor_repo,
    ):
        await repo._replace_anchors_for_check_result(cr=cr, anchors=anchors)

    anchor_repo.replace_for_check_result.assert_awaited_once()
    # primary = exact_span (index 1) -> set_primary с его row.id
    anchor_repo.set_primary.assert_awaited_once_with(
        check_result_id=cr.id,
        anchor_id=anchor_row_1.id,
    )
    assert cr.primary_anchor_id == anchor_row_1.id
    assert cr.primary_anchor_method == CheckAnchorMethod.EXACT_SPAN.value
    assert cr.primary_anchor_confidence == 1.0
    assert cr.anchor_stale is False


async def test_over_limit_applies_truncation():
    session = AsyncMock()
    repo = ResultRepository(session)
    cr = _mock_cr()

    anchors = [_a("page_only", 0.3, quote=f"p{i}") for i in range(8)]
    anchors.append(_a("exact_span", 1.0, quote="e"))

    # replace получит 5 anchors (limit)
    created = [MagicMock(id=uuid.uuid4()) for _ in range(5)]

    anchor_repo = AsyncMock()
    anchor_repo.replace_for_check_result = AsyncMock(return_value=created)
    anchor_repo.set_primary = AsyncMock(return_value=created[0])

    with patch(
        "db.repositories.result_repo.CheckResultAnchorRepository",
        return_value=anchor_repo,
    ):
        await repo._replace_anchors_for_check_result(cr=cr, anchors=anchors)

    call_kwargs = anchor_repo.replace_for_check_result.call_args.kwargs
    assert len(call_kwargs["anchors"]) == 5
    # primary — exact_span, который должен попасть в топ
    assert cr.primary_anchor_method == CheckAnchorMethod.EXACT_SPAN.value

    