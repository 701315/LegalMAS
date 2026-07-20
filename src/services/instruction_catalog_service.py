# src/services/instruction_catalog_service.py

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classifiers.yaml_registry import YAMLRegistry
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)


@dataclass(slots=True)
class InstructionCatalogItemData:
    doc_type_code: str
    name: str
    category: str | None
    risk_level: str | None
    language: str | None
    jurisdiction: str | None
    is_registry_available: bool
    total_versions_count: int
    draft_versions_count: int
    has_published: bool
    latest_version_id: str | None
    latest_version_status: str | None
    latest_version_updated_at: Any | None
    latest_published_version_id: str | None
    latest_published_at: Any | None
    latest_published_immutable_content_hash: str | None
    latest_draft_version_id: str | None
    latest_draft_is_valid: bool | None
    latest_draft_updated_at: Any | None


class InstructionCatalogService:
    """
    Read-only service для catalog/dashboard UI.

    Источники:
    - YAMLRegistry -> "какие doc types вообще доступны платформе"
    - persisted instruction versions -> "что уже создано/опубликовано"
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.version_repo = DocumentTypeInstructionVersionRepository(session)

    async def list_doc_type_catalog(self) -> list[InstructionCatalogItemData]:
        registry = YAMLRegistry.get_instance()
        registry_configs = {
            str(cfg.type_code): cfg
            for cfg in registry.get_all_configs()
        }

        versions = await self.version_repo.list_all_versions()

        grouped: dict[str, list] = defaultdict(list)
        for version in versions:
            grouped[str(version.doc_type_code)].append(version)

        all_doc_type_codes = set(registry_configs.keys()) | set(grouped.keys())

        items: list[InstructionCatalogItemData] = []

        for doc_type_code in all_doc_type_codes:
            cfg = registry_configs.get(doc_type_code)
            version_list = grouped.get(doc_type_code, [])

            latest_version = version_list[0] if version_list else None
            latest_published = next(
                (v for v in version_list if v.version_status == "published"),
                None,
            )
            latest_draft = next(
                (v for v in version_list if v.version_status == "draft"),
                None,
            )

            item = InstructionCatalogItemData(
                doc_type_code=doc_type_code,
                name=(
                    (latest_version.name if latest_version and latest_version.name else None)
                    or (cfg.name if cfg else None)
                    or doc_type_code
                ),
                category=(getattr(cfg, "category", None) if cfg else None),
                risk_level=(getattr(cfg, "risk_level", None) if cfg else None),
                language=(getattr(cfg, "language", None) if cfg else None),
                jurisdiction=(getattr(cfg, "jurisdiction", None) if cfg else None),
                is_registry_available=cfg is not None,
                total_versions_count=len(version_list),
                draft_versions_count=sum(
                    1 for v in version_list if v.version_status == "draft"
                ),
                has_published=latest_published is not None,
                latest_version_id=str(latest_version.id) if latest_version else None,
                latest_version_status=(
                    str(latest_version.version_status) if latest_version else None
                ),
                latest_version_updated_at=(
                    getattr(latest_version, "updated_at", None)
                    if latest_version
                    else None
                ),
                latest_published_version_id=(
                    str(latest_published.id) if latest_published else None
                ),
                latest_published_at=(
                    latest_published.published_at if latest_published else None
                ),
                latest_published_immutable_content_hash=(
                    latest_published.immutable_content_hash if latest_published else None
                ),
                latest_draft_version_id=(
                    str(latest_draft.id) if latest_draft else None
                ),
                latest_draft_is_valid=self._extract_validation_is_valid(latest_draft),
                latest_draft_updated_at=(
                    getattr(latest_draft, "updated_at", None)
                    if latest_draft
                    else None
                ),
            )
            items.append(item)

        items.sort(
            key=lambda x: (
                (x.category or "").lower(),
                (x.name or x.doc_type_code).lower(),
                x.doc_type_code.lower(),
            )
        )
        return items

    def _extract_validation_is_valid(
        self,
        version,
    ) -> bool | None:
        if version is None:
            return None

        report = getattr(version, "validation_report", None)
        if not isinstance(report, dict):
            return None

        value = report.get("is_valid")
        if value is None:
            return None

        return bool(value)
    

    