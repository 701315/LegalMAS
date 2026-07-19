# src/services/effective_instruction_service.py

"""
Effective instruction service.

Собирает единый, человекочитаемый список checks (global + doc-type),
которые были фактически применены к конкретному документу в конкретном Run.
Источник — frozen snapshots (PlaybookVersion.compiled_checks,
Run.instruction_snapshot_payload), а не живые файлы на диске.

Read-only: не влияет на исполнение checks.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from engine.doc_type_checks.loader import DatabaseInstructionProvider, DocTypeCheckLoader
from engine.playbook.loader import load_playbook_from_version

logger = get_logger(__name__)


class EffectiveInstructionNotFoundError(Exception):
    """Run или Document не найдены, либо документ не принадлежит сделке этого Run."""


class EffectiveInstructionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = RunRepository(session)
        self.doc_repo = DocumentRepository(session)
        self.playbook_repo = PlaybookRepository(session)

    async def get_for_document(
        self,
        *,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> dict[str, Any]:
        run = await self.run_repo.get(run_id)
        if run is None:
            raise EffectiveInstructionNotFoundError(f"Run not found: {run_id}")

        doc = await self.doc_repo.get_by_id(document_id)
        if doc is None or getattr(doc, "deal_id", None) != run.deal_id:
            raise EffectiveInstructionNotFoundError(
                f"Document not found or does not belong to this Run's deal: {document_id}"
            )

        doc_type = str(getattr(doc, "doc_type", "") or "").strip()
        triggers = sorted(getattr(doc, "applicable_triggers", None) or [])

        global_checks = await self._get_global_checks(run.playbook_version_id, doc_type, triggers)
        doc_type_checks, doc_type_version_id, is_frozen = self._get_doc_type_checks(
            run, doc_type, triggers
        )

        return {
            "run_id": str(run_id),
            "document_id": str(document_id),
            "doc_type": doc_type or None,
            "triggers": triggers,
            "playbook_version_id": str(run.playbook_version_id),
            "global_checks": global_checks,
            "doc_type_instruction_version_id": doc_type_version_id,
            "doc_type_checks": doc_type_checks,
            "is_frozen_snapshot": is_frozen,
        }

    async def _get_global_checks(
        self,
        playbook_version_id: uuid.UUID,
        doc_type: str,
        triggers: list[str],
    ) -> list[dict[str, Any]]:
        pb_version = await self.playbook_repo.get_by_id(playbook_version_id)
        if pb_version is None:
            logger.warning(
                "effective_instruction_service: playbook_version not found",
                playbook_version_id=str(playbook_version_id),
            )
            return []

        playbook = load_playbook_from_version(pb_version)
        checks = playbook.get_conditional_checks(doc_type or None, triggers)
        return [self._serialize_check(c, origin="global") for c in checks]

    def _get_doc_type_checks(
        self,
        run: Any,
        doc_type: str,
        triggers: list[str],
    ) -> tuple[list[dict[str, Any]], str | None, bool]:
        if not doc_type:
            return [], None, False

        instruction_versions = getattr(run, "instruction_versions", None) or {}
        snapshot_payload = getattr(run, "instruction_snapshot_payload", None) or {}
        version_id = instruction_versions.get(doc_type)

        if doc_type in snapshot_payload:
            loader = DocTypeCheckLoader(
                provider=DatabaseInstructionProvider({doc_type: snapshot_payload[doc_type]})
            )
            is_frozen = True
        else:
            logger.info(
                "effective_instruction_service: no frozen snapshot for doc_type, "
                "falling back to FilesystemInstructionProvider",
                run_id=str(run.id),
                doc_type=doc_type,
            )
            loader = DocTypeCheckLoader()
            is_frozen = False

        checks = loader.load_checks_for_doc(doc_type, triggers)

        return (
            [self._serialize_check(c, origin="document_type") for c in checks],
            version_id,
            is_frozen,
        )

    @staticmethod
    def _serialize_check(check: Any, *, origin: str) -> dict[str, Any]:
        return {
            "check_id": getattr(check, "id", None),
            "name": getattr(check, "name", None),
            "severity": getattr(check, "severity", None),
            "description": getattr(check, "description", None),
            "detector_type": getattr(getattr(check, "detector_type", None), "value", None),
            "conditional": bool(getattr(check, "conditional", None)),
            "origin": getattr(check, "origin", None) or origin,
        }
    
    
