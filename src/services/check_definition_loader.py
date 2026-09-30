# src/services/check_definition_loader.py

"""
Единый сборщик CheckDefinition для конкретного run.

Проблема, которую решает модуль:
  Endpoint /dd-requests (и /conditional-checks) строит checks_by_id
  только из playbook.checks. В этой коллекции лежат ИСКЛЮЧИТЕЛЬНО
  global checks (origin=GLOBAL_PLAYBOOK). Doc-type checks
  (origin=DOCUMENT_TYPE) хранятся отдельно — в
  DocumentTypeInstructionVersion.compiled_payload — и в playbook.checks
  не попадают. В результате ~90% check_def отсутствуют; downstream
  код (build_dd_requests) не может матчить check_result.check_id
  → CheckDefinition, и логика, завязанная на CheckDefinition.extraction,
  skip'ается для всех doc-type checks.

Решение:
  load_check_definitions_for_run() собирает CheckDefinition из ДВУХ
  источников:
    1. playbook_checks — global checks (origin=GLOBAL_PLAYBOOK);
    2. Run.instruction_versions → DocumentTypeInstructionVersion
       → compiled_payload → DocTypeCheckLoader.load_all_checks_for_doc
       для каждого doc_type.
  Возвращает {check_id: CheckDefinition}.

Совместимость:
  - Источник #2 активируется только если у run есть instruction_versions
    (persisted snapshots, введены вместе с DD Grid V1).
  - Для legacy-runs без snapshot'ов функция возвращает только global
    checks — как было до этого изменения.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.run import Run
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
)
from engine.playbook.models import CheckDefinition

logger = get_logger(__name__)


async def load_check_definitions_for_run(
    *,
    session: AsyncSession,
    run: Run,
    playbook_checks: list[CheckDefinition],
    doc_types: list[str] | None = None,
) -> dict[str, CheckDefinition]:
    """
    Собрать {check_id: CheckDefinition} из global + doc-type источников.

    Args:
        session:          AsyncSession в рамках текущего UoW.
        run:              ORM Run (нужен instruction_versions).
        playbook_checks:  list[CheckDefinition] из playbook.checks
                          (только origin=GLOBAL_PLAYBOOK).
        doc_types:        Ограничить doc_types. Если None — все из
                          run.instruction_versions.

    Returns:
        dict {check_id: CheckDefinition}. При конфликте id между global
        и doc-type приоритет у doc-type (он ближе к конкретному run'у).
    """
    checks_by_id: dict[str, CheckDefinition] = {
        c.id: c for c in playbook_checks
    }

    instruction_versions = getattr(run, "instruction_versions", None) or {}
    if not instruction_versions:
        logger.debug(
            "check_definition_loader: run has no instruction_versions, "
            "returning global checks only",
            run_id=str(run.id),
            global_count=len(checks_by_id),
        )
        return checks_by_id

    target_doc_types: list[str]
    if doc_types is not None:
        target_doc_types = [dt for dt in doc_types if dt in instruction_versions]
    else:
        target_doc_types = list(instruction_versions.keys())

    if not target_doc_types:
        return checks_by_id

    repo = DocumentTypeInstructionVersionRepository(session)
    compiled_map: dict[str, dict[str, Any]] = {}

    for doc_type in target_doc_types:
        version_id_str = instruction_versions.get(doc_type)
        if not version_id_str:
            continue
        try:
            version_uuid = uuid.UUID(str(version_id_str))
        except (ValueError, TypeError):
            logger.warning(
                "check_definition_loader: invalid instruction_version id",
                doc_type=doc_type,
                version_id=str(version_id_str),
            )
            continue

        try:
            version_obj = await repo.get_by_id(version_uuid)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "check_definition_loader: failed to load instruction version",
                doc_type=doc_type,
                version_id=str(version_uuid),
                error=str(exc),
            )
            continue

        if version_obj is None or not version_obj.compiled_payload:
            logger.warning(
                "check_definition_loader: instruction version missing or empty payload",
                doc_type=doc_type,
                version_id=str(version_uuid),
            )
            continue

        compiled_map[doc_type] = version_obj.compiled_payload

    if not compiled_map:
        logger.debug(
            "check_definition_loader: no compiled payloads resolved, "
            "returning global checks only",
            run_id=str(run.id),
        )
        return checks_by_id

    provider = DatabaseInstructionProvider(compiled_map)
    loader = DocTypeCheckLoader(provider=provider)

    doc_type_count = 0
    for doc_type in compiled_map.keys():
        try:
            doc_checks = loader.load_all_checks_for_doc(doc_type=doc_type)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "check_definition_loader: loader failed for doc_type",
                doc_type=doc_type,
                error=str(exc),
            )
            continue

        for check_def in doc_checks or []:
            cid = getattr(check_def, "id", None)
            if not cid:
                continue
            checks_by_id[cid] = check_def
            doc_type_count += 1

    logger.info(
        "check_definition_loader: resolved check definitions",
        run_id=str(run.id),
        global_count=len(playbook_checks),
        doc_type_count=doc_type_count,
        total_count=len(checks_by_id),
        doc_types=list(compiled_map.keys()),
    )
    return checks_by_id
