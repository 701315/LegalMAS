# src/engine/checks/instruction_snapshot.py

"""
Instruction snapshot service.

Зачем нужен этот модуль:
- фиксирует frozen snapshot doc-type инструкций для Run ДО планирования и
  выполнения checks, используя реальные doc_type документов сделки;
- гарантирует, что все worker-таски исполняются по одной зафиксированной
  версии инструкции, а не по живому YAML на диске в момент выполнения;
- предоставляет build_doc_type_loader() — фабрику DocTypeCheckLoader,
  который читает из БД (DatabaseInstructionProvider), а не с диска,
  когда для Run есть frozen snapshot.

Используется в:
- workers/check_runner_worker.py::run_deal_checks (freeze до plan_checks_for_run)
- workers/check_runner_worker.py::run_single_check (build_doc_type_loader для CheckRunner)
"""

from __future__ import annotations

import uuid
from typing import Any

from classifiers.yaml_registry import YAMLRegistry
from core.logging import get_logger
from core.pipeline_snapshots import RunSnapshot
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.repositories.run_repo import RunRepository
from engine.doc_type_checks.loader import DatabaseInstructionProvider, DocTypeCheckLoader

logger = get_logger(__name__)


async def freeze_instruction_snapshot(
    *,
    run_uuid: uuid.UUID,
    doc_types: set[str],
    run_repo: RunRepository,
    session: Any,
) -> dict[str, str]:
    """
    Зафиксировать frozen snapshot doc-type инструкций для Run.

    Для каждого уникального doc_type:
    - получает DocumentTypeConfig из YAMLRegistry (singleton, thread-safe);
    - резолвит или создаёт DocumentTypeInstructionVersion;
    - сохраняет cfg.raw (полный YAML документа) как payload для БД-провайдера.

    Args:
        run_uuid:  UUID запущенного Run.
        doc_types: Множество doc_type документов сделки (реальные документы,
                    не результат планирования — избегаем циклической зависимости
                    "план нужен для снапшота, снапшот нужен для плана").
        run_repo:  RunRepository в рамках текущего UoW.
        session:   AsyncSession текущего UoW.

    Returns:
        {doc_type: version_id_str}. Пустой словарь, если нет typed документов
        или все резолюции упали.

    Raises:
        Не поднимает исключений — все ошибки логируются как warning.
        Caller оборачивает вызов в try/except для непредвиденных ошибок сессии.
    """
    run_id_str = str(run_uuid)

    unique_doc_types = {
        dt.strip()
        for dt in doc_types
        if dt and isinstance(dt, str) and dt.strip().lower() != "unknown"
    }

    logger.info(
        "freeze_instruction_snapshot: collected unique doc_types",
        run_id=run_id_str,
        unique_doc_types_count=len(unique_doc_types),
        unique_doc_types=sorted(unique_doc_types)[:20],
    )

    if not unique_doc_types:
        logger.info(
            "freeze_instruction_snapshot: no typed documents, writing empty snapshot",
            run_id=run_id_str,
        )
        await run_repo.update_instruction_snapshot(run_uuid, {}, {}, {})
        return {}

    registry = YAMLRegistry.get_instance()
    version_repo = DocumentTypeInstructionVersionRepository(session)

    versions: dict[str, str] = {}
    manifest: dict[str, dict] = {}
    payload: dict[str, dict] = {}
    missing_configs: list[str] = []

    for doc_type in sorted(unique_doc_types):
        cfg = registry.get_config(doc_type)
        if cfg is None:
            logger.warning(
                "freeze_instruction_snapshot: doc_type not found in registry",
                run_id=run_id_str,
                doc_type=doc_type,
            )
            missing_configs.append(doc_type)
            continue

        try:
            result = await version_repo.resolve_or_create_from_config(cfg)
            version_id_str = str(result.version.id)
            raw_yaml = getattr(cfg, "raw", None) or {}

            versions[doc_type] = version_id_str
            manifest[doc_type] = {
                "version_id": version_id_str,
                "content_hash": getattr(cfg, "source_sha256", None),
                "override_id": None,
            }
            payload[doc_type] = raw_yaml

            logger.info(
                "freeze_instruction_snapshot: instruction version resolved",
                run_id=run_id_str,
                doc_type=doc_type,
                version_id=version_id_str,
                created=result.created,
                payload_keys=list(raw_yaml.keys())[:10],
            )

        except Exception as resolve_exc:
            logger.warning(
                "freeze_instruction_snapshot: failed to resolve version for doc_type",
                run_id=run_id_str,
                doc_type=doc_type,
                error=str(resolve_exc),
                error_type=type(resolve_exc).__name__,
            )
            missing_configs.append(doc_type)

    await run_repo.update_instruction_snapshot(run_uuid, versions, manifest, payload)

    logger.info(
        "freeze_instruction_snapshot: completed",
        run_id=run_id_str,
        fixed_count=len(versions),
        fixed_doc_types=sorted(versions.keys())[:20],
        missing_count=len(missing_configs),
        missing_doc_types=sorted(missing_configs)[:10],
    )

    return versions


def build_doc_type_loader(run_snap: RunSnapshot) -> DocTypeCheckLoader:
    """
    Построить DocTypeCheckLoader для исполнения checks в рамках Run.

    Если у Run есть frozen instruction_snapshot_payload (непустой) —
    используем DatabaseInstructionProvider поверх зафиксированных данных
    (гарантированная воспроизводимость: тот же payload, что был на момент
    запуска Run, независимо от изменений YAML на диске позже).

    Иначе (старые Run без снапшота, или снапшот пуст/не был зафиксирован
    из-за ошибки в freeze_instruction_snapshot) — fallback на дефолтный
    FilesystemInstructionProvider (текущие YAML на диске).

    Args:
        run_snap: RunSnapshot (из core.pipeline_snapshots.snapshot_run).

    Returns:
        DocTypeCheckLoader, готовый к передаче в CheckRunner(doc_type_loader=...).
    """
    payload = getattr(run_snap, "instruction_snapshot_payload", None)

    if payload:
        logger.debug(
            "build_doc_type_loader: using DatabaseInstructionProvider (frozen snapshot)",
            run_id=str(run_snap.id) if hasattr(run_snap, "id") else None,
            doc_types_count=len(payload),
        )
        return DocTypeCheckLoader(provider=DatabaseInstructionProvider(payload))

    logger.debug(
        "build_doc_type_loader: no frozen snapshot, falling back to FilesystemInstructionProvider",
    )
    return DocTypeCheckLoader()


