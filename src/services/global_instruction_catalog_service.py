# src/services/global_instruction_catalog_service.py

"""
Global instruction catalog service.
Зеркало InstructionCatalogService, но без YAMLRegistry
(у global instructions нет registry.yaml).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)


@dataclass(slots=True)
class GlobalInstructionCatalogItemData:
    instruction_code: str
    name: str
    group: str | None
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
    owner_scope: str = "platform"


class GlobalInstructionCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GlobalInstructionVersionRepository(session)

    async def list_catalog(self) -> list[GlobalInstructionCatalogItemData]:
        """
        Platform admin catalog.
        Все platform-scope global instructions, сгруппированные по instruction_code.
        Сортировка: по group (nulls last), затем по name.
        """
        versions = await self.repo.list_platform_versions()

        grouped: dict[str, list] = defaultdict(list)
        for v in versions:
            grouped[v.instruction_code].append(v)

        items: list[GlobalInstructionCatalogItemData] = []
        for instruction_code, version_list in grouped.items():
            item = self._build_item(
                instruction_code=instruction_code,
                version_list=version_list,
            )
            items.append(item)

        items.sort(
            key=lambda x: (
                (x.group or "zzz_ungrouped").lower(),
                x.name.lower(),
                x.instruction_code.lower(),
            )
        )
        return items

    def _build_item(
        self,
        *,
        instruction_code: str,
        version_list: list,
    ) -> GlobalInstructionCatalogItemData:
        # list_platform_versions возвращает уже отсортированный created_at DESC
        latest = version_list[0] if version_list else None
        latest_published = next(
            (v for v in version_list if v.version_status == "published"), None
        )
        latest_draft = next(
            (v for v in version_list if v.version_status == "draft"), None
        )

        name = (
            (latest.name if latest and latest.name else None)
            or instruction_code
        )
        group = latest.group if latest else None

        return GlobalInstructionCatalogItemData(
            instruction_code=instruction_code,
            name=name,
            group=group,
            total_versions_count=len(version_list),
            draft_versions_count=sum(
                1 for v in version_list if v.version_status == "draft"
            ),
            has_published=latest_published is not None,
            latest_version_id=str(latest.id) if latest else None,
            latest_version_status=latest.version_status if latest else None,
            latest_version_updated_at=(
                getattr(latest, "updated_at", None) if latest else None
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
            latest_draft_is_valid=self._extract_is_valid(latest_draft),
            latest_draft_updated_at=(
                getattr(latest_draft, "updated_at", None) if latest_draft else None
            ),
        )

    def _extract_is_valid(self, version) -> bool | None:
        if version is None:
            return None
        report = getattr(version, "validation_report", None)
        if not isinstance(report, dict):
            return None
        value = report.get("is_valid")
        if value is None:
            return None
        return bool(value)


    