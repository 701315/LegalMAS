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

Strict mode (snapshot_schema_version >= 1):
- payload содержит compiled_payload из persisted DocumentTypeInstructionVersion;
- filesystem fallback запрещён;
- отсутствие payload для doc_type = ConfigurationIntegrityError.

Legacy mode (snapshot_schema_version IS NULL):
- filesystem fallback разрешён;
- is_reproducible = False.

Snapshot фиксируется атомарно одним вызовом update_instruction_snapshot
включая snapshot_schema_version — нет промежуточного состояния.
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
from engine.checks.snapshot_policy import (
    SNAPSHOT_SCHEMA_VERSION_CURRENT,
    resolve_doc_type_payload,
)
from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
    FilesystemInstructionProvider,
)
from services.instruction_compiler import InstructionCompiler

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
    - получает DocumentTypeConfig из YAMLRegistry;
    - резолвит или создаёт DocumentTypeInstructionVersion;
    - сохраняет compiled_payload (не raw) как payload.

    Атомарно выставляет snapshot_schema_version=1 вместе со snapshot —
    нет промежуточного состояния между "snapshot записан" и "version выставлена".

    Returns:
        {doc_type: version_id_str}
    """
    run_id_str = str(run_uuid)
    compiler = InstructionCompiler()

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
        await run_repo.update_instruction_snapshot(
            run_uuid,
            {},
            {},
            {},
            snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_CURRENT,
        )
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

            compiled_payload = result.version.compiled_payload
            if not compiled_payload:
                try:
                    compiled = compiler.compile_doc_type_instruction(
                        doc_type_code=doc_type,
                        source=result.version.source_yaml or cfg.raw,
                    )
                    compiled_payload = compiled.compiled_payload
                except Exception as compile_exc:
                    logger.warning(
                        "freeze_instruction_snapshot: compile fallback failed, using raw",
                        run_id=run_id_str,
                        doc_type=doc_type,
                        error=str(compile_exc),
                    )
                    compiled_payload = getattr(cfg, "raw", None) or {}

            content_hash = (
                result.version.immutable_content_hash
                or getattr(cfg, "source_sha256", None)
            )

            versions[doc_type] = version_id_str
            manifest[doc_type] = {
                "version_id": version_id_str,
                "content_hash": content_hash,
                "override_id": None,
                "schema_version": SNAPSHOT_SCHEMA_VERSION_CURRENT,
            }
            payload[doc_type] = compiled_payload

            logger.info(
                "freeze_instruction_snapshot: instruction version resolved",
                run_id=run_id_str,
                doc_type=doc_type,
                version_id=version_id_str,
                created=result.created,
                has_compiled_payload=bool(compiled_payload),
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

    # Атомарная запись snapshot + schema_version в одном UPDATE
    await run_repo.update_instruction_snapshot(
        run_uuid,
        versions,
        manifest,
        payload,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_CURRENT,
    )

    logger.info(
        "freeze_instruction_snapshot: completed, snapshot_schema_version=%d",
        SNAPSHOT_SCHEMA_VERSION_CURRENT,
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

    Strict mode (snapshot_schema_version >= 1):
    - payload обязателен;
    - filesystem fallback ЗАПРЕЩЁН;
    - возвращает loader с DatabaseInstructionProvider.

    Legacy mode (snapshot_schema_version IS NULL):
    - если payload есть — используем DatabaseInstructionProvider;
    - если payload нет — filesystem fallback с предупреждением.
    """
    payload = getattr(run_snap, "instruction_snapshot_payload", None)
    is_strict = getattr(run_snap, "is_strict_snapshot", False)
    run_id = str(run_snap.id) if hasattr(run_snap, "id") else "unknown"

    if is_strict:
        if not payload:
            from engine.checks.snapshot_policy import ConfigurationIntegrityError
            raise ConfigurationIntegrityError(
                run_id=run_id,
                doc_type="<all>",
            )
        logger.debug(
            "build_doc_type_loader: strict mode, using DatabaseInstructionProvider",
            run_id=run_id,
            doc_types_count=len(payload),
        )
        return DocTypeCheckLoader(provider=DatabaseInstructionProvider(payload))

    if payload:
        logger.debug(
            "build_doc_type_loader: legacy mode with payload, using DatabaseInstructionProvider",
            run_id=run_id,
            doc_types_count=len(payload),
        )
        return DocTypeCheckLoader(provider=DatabaseInstructionProvider(payload))

    logger.warning(
        "build_doc_type_loader: legacy mode without payload, "
        "falling back to FilesystemInstructionProvider. "
        "This run is not reproducible.",
        run_id=run_id,
    )
    return DocTypeCheckLoader(provider=FilesystemInstructionProvider())


