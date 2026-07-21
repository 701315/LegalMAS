from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.playbook import Playbook, PlaybookLineItem
from db.repositories.playbook_repo import PlaybookRepository


@pytest.fixture
def session():
    s = MagicMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.execute = AsyncMock()
    s.delete = AsyncMock()
    return s


@pytest.mark.asyncio
async def test_create_line_with_items_stores_instruction_code(session):
    repo = PlaybookRepository(session)

    items = [
        {
            "kind": "check",
            "instruction_code": "encumbrances_warranty",
            "order_index": 10,
        },
        {
            "kind": "check",
            "instruction_code": "change_of_control",
            "order_index": 20,
        },
    ]

    line, line_items = await repo.create_line_with_items(
        title="M&A RU Core",
        description="Core template",
        deal_type="mna",
        jurisdiction="RU",
        language="ru",
        items=items,
    )

    assert isinstance(line, Playbook)
    assert len(line_items) == 2
    assert all(isinstance(item, PlaybookLineItem) for item in line_items)
    assert line_items[0].instruction_code == "encumbrances_warranty"
    assert line_items[1].instruction_code == "change_of_control"
    assert line_items[0].kind == "check"
    assert line_items[1].kind == "check"


    