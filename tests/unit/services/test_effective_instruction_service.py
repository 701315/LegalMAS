"""
Unit-тесты для EffectiveInstructionService.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.effective_instruction_service import (
    EffectiveInstructionNotFoundError,
    EffectiveInstructionService,
)


@pytest.fixture
def service():
    session = MagicMock()
    svc = EffectiveInstructionService(session)
    svc.run_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.playbook_repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_get_for_document_run_not_found(service):
    service.run_repo.get = AsyncMock(return_value=None)

    with pytest.raises(EffectiveInstructionNotFoundError, match="Run not found"):
        await service.get_for_document(run_id=uuid.uuid4(), document_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_get_for_document_doc_not_found(service):
    fake_run = MagicMock(deal_id=uuid.uuid4())
    service.run_repo.get = AsyncMock(return_value=fake_run)
    service.doc_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(EffectiveInstructionNotFoundError, match="Document not found"):
        await service.get_for_document(run_id=uuid.uuid4(), document_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_get_for_document_doc_belongs_to_different_deal(service):
    run_deal_id = uuid.uuid4()
    other_deal_id = uuid.uuid4()
    fake_run = MagicMock(deal_id=run_deal_id)
    fake_doc = MagicMock(deal_id=other_deal_id)

    service.run_repo.get = AsyncMock(return_value=fake_run)
    service.doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

    with pytest.raises(EffectiveInstructionNotFoundError):
        await service.get_for_document(run_id=uuid.uuid4(), document_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_get_for_document_frozen_snapshot_used(service):
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    pb_version_id = uuid.uuid4()

    fake_run = MagicMock(
        id=run_id,
        deal_id=deal_id,
        playbook_version_id=pb_version_id,
        instruction_versions={"nda": "v1"},
        instruction_snapshot_payload={
            "nda": {
                "checks_v8": [
                    {
                        "id": "chk_1",
                        "name": "Check 1",
                        "detector_type": "rules",
                        "rules": {"keywords": ["confidentiality", "non-disclosure"]},
                    }
                ]
            }
        },
    )
    fake_doc = MagicMock(deal_id=deal_id, doc_type="nda", applicable_triggers=["trg_1"])
    fake_pb_version = MagicMock()

    service.run_repo.get = AsyncMock(return_value=fake_run)
    service.doc_repo.get_by_id = AsyncMock(return_value=fake_doc)
    service.playbook_repo.get_by_id = AsyncMock(return_value=fake_pb_version)

    fake_playbook = MagicMock()
    fake_playbook.get_conditional_checks.return_value = []

    with patch(
        "services.effective_instruction_service.load_playbook_from_version",
        return_value=fake_playbook,
    ):
        result = await service.get_for_document(run_id=run_id, document_id=doc_id)

    assert result["is_frozen_snapshot"] is True
    assert result["doc_type"] == "nda"
    assert result["doc_type_instruction_version_id"] == "v1"
    assert len(result["doc_type_checks"]) == 1
    assert result["doc_type_checks"][0]["check_id"] == "chk_1"
    assert result["doc_type_checks"][0]["origin"] == "document_type"


@pytest.mark.asyncio
async def test_get_for_document_no_snapshot_falls_back(service):
    run_id = uuid.uuid4()
    deal_id = uuid.uuid4()

    fake_run = MagicMock(
        id=run_id,
        deal_id=deal_id,
        playbook_version_id=uuid.uuid4(),
        instruction_versions={},
        instruction_snapshot_payload={},
        snapshot_schema_version=None,  # legacy run
    )

    fake_doc = MagicMock(deal_id=deal_id, doc_type="spa", applicable_triggers=[])

    service.run_repo.get = AsyncMock(return_value=fake_run)
    service.doc_repo.get_by_id = AsyncMock(return_value=fake_doc)
    service.playbook_repo.get_by_id = AsyncMock(return_value=MagicMock())

    fake_playbook = MagicMock()
    fake_playbook.get_conditional_checks.return_value = []

    with patch(
        "services.effective_instruction_service.load_playbook_from_version",
        return_value=fake_playbook,
    ), patch(
        "services.effective_instruction_service.DocTypeCheckLoader"
    ) as mock_loader_cls:
        mock_loader = MagicMock()
        mock_loader.load_checks_for_doc.return_value = []
        mock_loader_cls.return_value = mock_loader

        result = await service.get_for_document(run_id=run_id, document_id=uuid.uuid4())

    assert result["is_frozen_snapshot"] is False
    assert result["doc_type_instruction_version_id"] is None




@pytest.mark.asyncio
async def test_get_for_document_no_doc_type_skips_doc_type_checks(service):
    run_id = uuid.uuid4()
    deal_id = uuid.uuid4()

    fake_run = MagicMock(
        id=run_id, deal_id=deal_id, playbook_version_id=uuid.uuid4(),
        instruction_versions={}, instruction_snapshot_payload={},
        snapshot_schema_version=None,  # legacy run
    )
    fake_doc = MagicMock(deal_id=deal_id, doc_type=None, applicable_triggers=[])

    service.run_repo.get = AsyncMock(return_value=fake_run)
    service.doc_repo.get_by_id = AsyncMock(return_value=fake_doc)
    service.playbook_repo.get_by_id = AsyncMock(return_value=MagicMock())

    fake_playbook = MagicMock()
    fake_playbook.get_conditional_checks.return_value = []

    with patch(
        "services.effective_instruction_service.load_playbook_from_version",
        return_value=fake_playbook,
    ):
        result = await service.get_for_document(run_id=run_id, document_id=uuid.uuid4())

    assert result["doc_type_checks"] == []
    assert result["doc_type_instruction_version_id"] is None

    