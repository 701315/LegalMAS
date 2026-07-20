from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.instruction_catalog_service import InstructionCatalogService


def _cfg(
    *,
    type_code: str,
    name: str,
    category: str | None = None,
    risk_level: str | None = None,
    language: str | None = None,
    jurisdiction: str | None = None,
):
    return SimpleNamespace(
        type_code=type_code,
        name=name,
        category=category,
        risk_level=risk_level,
        language=language,
        jurisdiction=jurisdiction,
    )


def _version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    name: str = "NDA",
    version_status: str = "draft",
    validation_report: dict | None = None,
):
    return SimpleNamespace(
        id=version_id or uuid.uuid4(),
        doc_type_code=doc_type_code,
        name=name,
        version_status=version_status,
        immutable_content_hash="hash123" if version_status == "published" else None,
        published_at=datetime.now(UTC) if version_status == "published" else None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        validation_report=validation_report,
    )


@pytest.mark.asyncio
class TestInstructionCatalogService:
    async def test_registry_only_doc_type_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_registry = SimpleNamespace(
            get_all_configs=lambda: [
                _cfg(
                    type_code="nda",
                    name="NDA",
                    category="contract",
                    risk_level="medium",
                    language="en",
                    jurisdiction="EN",
                )
            ]
        )

        monkeypatch.setattr(
            "services.instruction_catalog_service.YAMLRegistry.get_instance",
            lambda: fake_registry,
        )

        async def fake_list_all_versions(self):
            return []

        monkeypatch.setattr(
            "services.instruction_catalog_service.DocumentTypeInstructionVersionRepository.list_all_versions",
            fake_list_all_versions,
        )

        service = InstructionCatalogService(MagicMock())
        items = await service.list_doc_type_catalog()

        assert len(items) == 1
        assert items[0].doc_type_code == "nda"
        assert items[0].name == "NDA"
        assert items[0].total_versions_count == 0
        assert items[0].has_published is False
        assert items[0].is_registry_available is True

    async def test_catalog_merges_registry_and_versions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_registry = SimpleNamespace(
            get_all_configs=lambda: [
                _cfg(type_code="nda", name="NDA", category="contract"),
            ]
        )

        monkeypatch.setattr(
            "services.instruction_catalog_service.YAMLRegistry.get_instance",
            lambda: fake_registry,
        )

        versions = [
            _version(
                doc_type_code="nda",
                version_status="draft",
                validation_report={"is_valid": False},
            ),
            _version(
                doc_type_code="nda",
                version_status="published",
            ),
        ]

        async def fake_list_all_versions(self):
            return versions

        monkeypatch.setattr(
            "services.instruction_catalog_service.DocumentTypeInstructionVersionRepository.list_all_versions",
            fake_list_all_versions,
        )

        service = InstructionCatalogService(MagicMock())
        items = await service.list_doc_type_catalog()

        assert len(items) == 1
        item = items[0]
        assert item.doc_type_code == "nda"
        assert item.total_versions_count == 2
        assert item.draft_versions_count == 1
        assert item.has_published is True
        assert item.latest_version_status == "draft"
        assert item.latest_draft_is_valid is False
        assert item.latest_published_version_id is not None

    async def test_db_only_historical_doc_type_included(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_registry = SimpleNamespace(
            get_all_configs=lambda: []
        )

        monkeypatch.setattr(
            "services.instruction_catalog_service.YAMLRegistry.get_instance",
            lambda: fake_registry,
        )

        versions = [
            _version(
                doc_type_code="legacy_type",
                name="Legacy Type",
                version_status="archived",
            ),
        ]

        async def fake_list_all_versions(self):
            return versions

        monkeypatch.setattr(
            "services.instruction_catalog_service.DocumentTypeInstructionVersionRepository.list_all_versions",
            fake_list_all_versions,
        )

        service = InstructionCatalogService(MagicMock())
        items = await service.list_doc_type_catalog()

        assert len(items) == 1
        assert items[0].doc_type_code == "legacy_type"
        assert items[0].is_registry_available is False
        assert items[0].total_versions_count == 1


        