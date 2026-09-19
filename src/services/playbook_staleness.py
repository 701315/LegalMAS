# src/services/playbook_staleness.py
"""
Проверка устаревания playbook-версий по global-инструкциям.

Playbook хранит в compiled_checks.meta.global_instruction_refs снимок
{instruction_code -> version_id}. Если текущая published platform-версия
инструкции имеет другой id — playbook устарел и при новом run'е может
дать результат, отличный от ожидаемого.

Doc-type инструкции в этот расчёт не входят: они не снапшотятся в playbook,
а загружаются на момент run'а отдельно.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.global_instruction import GlobalInstructionVersion
from db.models.playbook import PlaybookVersion


async def _load_current_global_refs(db: AsyncSession) -> dict[str, str]:
    """{instruction_code -> published platform version_id}."""
    stmt = select(
        GlobalInstructionVersion.instruction_code,
        GlobalInstructionVersion.id,
    ).where(
        GlobalInstructionVersion.owner_scope == "platform",
        GlobalInstructionVersion.tenant_id.is_(None),
        GlobalInstructionVersion.version_status == "published",
    )
    result = await db.execute(stmt)
    return {row.instruction_code: str(row.id) for row in result}


def _extract_refs(pv: PlaybookVersion) -> dict[str, str]:
    compiled = pv.compiled_checks or {}
    meta = compiled.get("meta") or {}
    refs = meta.get("global_instruction_refs") or {}
    return {str(k): str(v) for k, v in refs.items()}


def _compute_outdated(
    refs: dict[str, str],
    current_refs: dict[str, str],
) -> list[dict[str, Any]]:
    """Список расхождений между snapshot playbook'а и текущими published."""
    outdated: list[dict[str, Any]] = []
    for code, ref_id in refs.items():
        current = current_refs.get(code)
        if current and current != ref_id:
            outdated.append(
                {
                    "instruction_code": code,
                    "playbook_ref": ref_id,
                    "current_ref": current,
                }
            )
    return outdated


async def compute_stale_playbooks(
    db: AsyncSession,
    *,
    user_tenant_id: uuid.UUID | None,
    is_superadmin: bool,
) -> dict[str, Any]:
    """
    Возвращает playbook-версии, у которых хотя бы одна global-инструкция
    обновилась после создания версии.

    Visibility:
    - superadmin  -> все версии (platform + все tenant)
    - иначе       -> platform + только свой tenant
    """
    stmt = select(PlaybookVersion)
    if not is_superadmin:
        if user_tenant_id is None:
            return {"total_visible": 0, "stale_count": 0, "stale": []}
        stmt = stmt.where(
            or_(
                PlaybookVersion.tenant_id == user_tenant_id,
                PlaybookVersion.tenant_id.is_(None),
            )
        )

    result = await db.execute(stmt)
    versions = list(result.scalars().all())

    current_refs = await _load_current_global_refs(db)

    stale: list[dict[str, Any]] = []
    for pv in versions:
        refs = _extract_refs(pv)
        if not refs:
            continue
        outdated = _compute_outdated(refs, current_refs)
        if not outdated:
            continue
        stale.append(
            {
                "playbook_version_id": str(pv.id),
                "playbook_id": str(pv.playbook_id) if pv.playbook_id else None,
                "name": pv.name,
                "semver": pv.semver,
                "status": pv.status,
                "owner_scope": pv.owner_scope,
                "created_at": pv.created_at.isoformat() if pv.created_at else None,
                "outdated_count": len(outdated),
                "total_refs": len(refs),
                "outdated_refs": outdated,
            }
        )

    stale.sort(key=lambda item: item["created_at"] or "", reverse=True)

    return {
        "total_visible": len(versions),
        "stale_count": len(stale),
        "stale": stale,
    }
