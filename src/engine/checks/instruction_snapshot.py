# src/engine/checks/instruction_snapshot.py

"""
Instruction snapshot service.

Зачем нужен этот модуль:
- фиксирует frozen snapshot doc-type инструкций для Run ДО планирования и
  выполнения checks, используя реальные doc_type документов сделки;
- гарантирует, что все worker-таски исполняются по одной зафиксированной
  effective-инструкции, а не по живому YAML/DB состоянию в момент выполнения;
- поддерживает canonical resolution chain:
    published base → tenant active override → deal active override;
- предоставляет build_doc_type_loader() — фабрику DocTypeCheckLoader,
  который читает из БД (DatabaseInstructionProvider), а не с диска,
  когда для Run есть frozen snapshot.

Resolution order:
1. Если tenant context доступен:
   - пытаемся резолвить canonical effective payload через
     InstructionOverrideService.resolve_effective_payload().
   - если published base version отсутствует, выполняем controlled fallback
     в registry-backed platform seed path.
2. Если tenant context недоступен:
   - сначала пытаемся взять latest published platform version из БД;
   - если published version отсутствует, используем registry-backed platform seed path.

Strict mode (snapshot_schema_version >= 1):
- payload содержит frozen effective compiled payload;
- filesystem fallback запрещён;
- отсутствие payload для doc_type = ConfigurationIntegrityError.

Legacy mode (snapshot_schema_version IS NULL):
- filesystem fallback разрешён;
- is_reproducible = False.

Snapshot фиксируется атомарно одним вызовом update_instruction_snapshot
включая snapshot_schema_version — нет промежуточного состояния.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from classifiers.yaml_registry import YAMLRegistry
from core.logging import get_logger
from core.pipeline_snapshots import RunSnapshot
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.repositories.run_repo import RunRepository
from engine.checks.snapshot_policy import SNAPSHOT_SCHEMA_VERSION_CURRENT
from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
    FilesystemInstructionProvider,
)
from engine.instructions.override_service import (
    BaseVersionNotFoundError,
    InstructionOverrideService,
)
from services.instruction_compiler import InstructionCompiler

logger = get_logger(__name__)


class InstructionSnapshotFreezeError(RuntimeError):
    """
    Фатальная ошибка freeze instruction snapshot.

    Инвариант strict snapshot:
    - snapshot должен быть полным для всех participating doc_types;
    - partial snapshot не пишется в БД.
    """

    def __init__(self, *, run_id: str, errors: list[dict[str, str]]):
        self.run_id = run_id
        self.errors = errors

        preview = ", ".join(
            f"{item['doc_type']}:{item['error_type']}" for item in errors[:5]
        )
        if len(errors) > 5:
            preview = f"{preview} (+{len(errors) - 5} more)"

        super().__init__(
            f"Failed to freeze instruction snapshot for run {run_id}: {preview}"
        )


@dataclass(frozen=True, slots=True)
class FrozenInstructionEntry:
    version_id: str
    manifest_entry: dict[str, Any]
    payload: dict[str, Any]


def _compute_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _build_manifest_entry(
    *,
    version_id: str,
    content_hash: str | None,
    effective_hash: str,
    resolution_strategy: str,
    override_id: str | None = None,
    tenant_override_id: str | None = None,
    deal_override_id: str | None = None,
    is_overridden: bool = False,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version_id": version_id,
        "content_hash": content_hash,
        "effective_hash": effective_hash,
        "override_id": override_id,
        "tenant_override_id": tenant_override_id,
        "deal_override_id": deal_override_id,
        "is_overridden": is_overridden,
        "resolution_strategy": resolution_strategy,
        "schema_version": SNAPSHOT_SCHEMA_VERSION_CURRENT,
        "provenance": provenance or {},
    }


def _ensure_compiled_payload(
    *,
    doc_type: str,
    compiler: InstructionCompiler,
    compiled_payload: dict[str, Any] | None,
    source: str | dict[str, Any] | None,
    fallback_payload: dict[str, Any] | None,
    run_id: str,
    resolution_source: str,
) -> dict[str, Any]:
    if compiled_payload is not None:
        return compiled_payload

    try:
        compiled = compiler.compile_doc_type_instruction(
            doc_type_code=doc_type,
            source=source or fallback_payload or {},
        )
        if compiled.compiled_payload is not None:
            return compiled.compiled_payload
    except Exception as compile_exc:
        logger.warning(
            "freeze_instruction_snapshot: compile fallback failed, using raw fallback payload",
            run_id=run_id,
            doc_type=doc_type,
            resolution_source=resolution_source,
            error=str(compile_exc),
            error_type=type(compile_exc).__name__,
        )

    return fallback_payload or {}


async def _resolve_effective_entry(
    *,
    doc_type: str,
    override_service: InstructionOverrideService,
    tenant_id: uuid.UUID,
    deal_id: uuid.UUID | None,
) -> FrozenInstructionEntry:
    effective = await override_service.resolve_effective_payload(
        doc_type_code=doc_type,
        tenant_id=tenant_id,
        deal_id=deal_id,
    )

    version_id_str = str(effective.base_version_id)
    tenant_override_id_str = (
        str(effective.tenant_override_id) if effective.tenant_override_id else None
    )
    deal_override_id_str = (
        str(effective.deal_override_id) if effective.deal_override_id else None
    )
    top_override_id = deal_override_id_str or tenant_override_id_str

    return FrozenInstructionEntry(
        version_id=version_id_str,
        manifest_entry=_build_manifest_entry(
            version_id=version_id_str,
            content_hash=effective.base_content_hash,
            effective_hash=effective.effective_hash,
            override_id=top_override_id,
            tenant_override_id=tenant_override_id_str,
            deal_override_id=deal_override_id_str,
            is_overridden=effective.is_overridden,
            resolution_strategy="effective_override_chain",
            provenance=effective.provenance,
        ),
        payload=effective.effective_payload or {},
    )


async def _resolve_published_platform_entry(
    *,
    doc_type: str,
    version_repo: DocumentTypeInstructionVersionRepository,
    registry: YAMLRegistry,
    compiler: InstructionCompiler,
    run_id: str,
) -> FrozenInstructionEntry | None:
    published_version = await version_repo.get_latest_published(
        doc_type,
        tenant_id=None,
    )
    if published_version is None:
        return None

    cfg = registry.get_config(doc_type)
    fallback_payload = getattr(cfg, "raw", None) if cfg is not None else None

    effective_payload = _ensure_compiled_payload(
        doc_type=doc_type,
        compiler=compiler,
        compiled_payload=published_version.compiled_payload,
        source=published_version.source_yaml,
        fallback_payload=fallback_payload,
        run_id=run_id,
        resolution_source="published_platform_base",
    )

    effective_hash = _compute_payload_hash(effective_payload)
    content_hash = (
        published_version.immutable_content_hash
        or published_version.source_sha256
        or effective_hash
    )
    version_id_str = str(published_version.id)

    provenance = {
        "base_version_id": version_id_str,
        "base_owner_scope": published_version.owner_scope,
        "base_content_hash": content_hash,
        "tenant_override_id": None,
        "deal_override_id": None,
        "is_overridden": False,
        "effective_hash": effective_hash,
    }

    return FrozenInstructionEntry(
        version_id=version_id_str,
        manifest_entry=_build_manifest_entry(
            version_id=version_id_str,
            content_hash=content_hash,
            effective_hash=effective_hash,
            override_id=None,
            tenant_override_id=None,
            deal_override_id=None,
            is_overridden=False,
            resolution_strategy="published_platform_base",
            provenance=provenance,
        ),
        payload=effective_payload,
    )


async def _resolve_registry_seed_entry(
    *,
    doc_type: str,
    registry: YAMLRegistry,
    version_repo: DocumentTypeInstructionVersionRepository,
    compiler: InstructionCompiler,
    run_id: str,
) -> FrozenInstructionEntry:
    cfg = registry.get_config(doc_type)
    if cfg is None:
        raise LookupError(
            f"Document type '{doc_type}' not found in YAMLRegistry and no published DB version exists"
        )

    result = await version_repo.resolve_or_create_from_config(cfg)
    effective_payload = _ensure_compiled_payload(
        doc_type=doc_type,
        compiler=compiler,
        compiled_payload=result.version.compiled_payload,
        source=result.version.source_yaml or cfg.raw,
        fallback_payload=getattr(cfg, "raw", None) or {},
        run_id=run_id,
        resolution_source="registry_seeded_base",
    )

    effective_hash = _compute_payload_hash(effective_payload)
    content_hash = (
        result.version.immutable_content_hash
        or result.version.source_sha256
        or getattr(cfg, "source_sha256", None)
        or effective_hash
    )
    version_id_str = str(result.version.id)

    provenance = {
        "base_version_id": version_id_str,
        "base_owner_scope": result.version.owner_scope,
        "base_content_hash": content_hash,
        "tenant_override_id": None,
        "deal_override_id": None,
        "is_overridden": False,
        "effective_hash": effective_hash,
        "registry_seed_created": result.created,
    }

    return FrozenInstructionEntry(
        version_id=version_id_str,
        manifest_entry=_build_manifest_entry(
            version_id=version_id_str,
            content_hash=content_hash,
            effective_hash=effective_hash,
            override_id=None,
            tenant_override_id=None,
            deal_override_id=None,
            is_overridden=False,
            resolution_strategy="registry_seeded_base",
            provenance=provenance,
        ),
        payload=effective_payload,
    )


async def _resolve_snapshot_entry(
    *,
    doc_type: str,
    tenant_id: uuid.UUID | None,
    deal_id: uuid.UUID | None,
    registry: YAMLRegistry,
    version_repo: DocumentTypeInstructionVersionRepository,
    override_service: InstructionOverrideService,
    compiler: InstructionCompiler,
    run_id: str,
) -> FrozenInstructionEntry:
    if tenant_id is not None:
        try:
            return await _resolve_effective_entry(
                doc_type=doc_type,
                override_service=override_service,
                tenant_id=tenant_id,
                deal_id=deal_id,
            )
        except BaseVersionNotFoundError:
            logger.info(
                "freeze_instruction_snapshot: no published base version found for effective chain, "
                "falling back to registry-backed seed path",
                run_id=run_id,
                doc_type=doc_type,
                tenant_id=str(tenant_id),
                deal_id=str(deal_id) if deal_id else None,
            )
            return await _resolve_registry_seed_entry(
                doc_type=doc_type,
                registry=registry,
                version_repo=version_repo,
                compiler=compiler,
                run_id=run_id,
            )

    published_platform_entry = await _resolve_published_platform_entry(
        doc_type=doc_type,
        version_repo=version_repo,
        registry=registry,
        compiler=compiler,
        run_id=run_id,
    )
    if published_platform_entry is not None:
        return published_platform_entry

    return await _resolve_registry_seed_entry(
        doc_type=doc_type,
        registry=registry,
        version_repo=version_repo,
        compiler=compiler,
        run_id=run_id,
    )


async def freeze_instruction_snapshot(
    *,
    run_uuid: uuid.UUID,
    doc_types: set[str],
    run_repo: RunRepository,
    session: Any,
    tenant_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
) -> dict[str, str]:
    """
    Зафиксировать frozen snapshot doc-type инструкций для Run.

    Canonical resolution order:
    1. tenant/deal effective payload через override chain;
    2. published platform base version из БД;
    3. controlled registry-backed seed fallback.

    Инварианты:
    - versions[{doc_type}] всегда указывает на БАЗОВУЮ instruction version,
      относительно которой был вычислен frozen payload;
    - payload[{doc_type}] содержит final effective compiled payload,
      уже после tenant/deal overrides;
    - manifest хранит provenance, override ids и effective hash;
    - snapshot пишется all-or-nothing: partial strict snapshot в БД не сохраняется.

    Returns:
        {doc_type: base_version_id_str}
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
        tenant_id=str(tenant_id) if tenant_id else None,
        deal_id=str(deal_id) if deal_id else None,
        unique_doc_types_count=len(unique_doc_types),
        unique_doc_types=sorted(unique_doc_types)[:20],
    )

    if not unique_doc_types:
        logger.info(
            "freeze_instruction_snapshot: no typed documents, writing empty snapshot",
            run_id=run_id_str,
        )
        updated_run = await run_repo.update_instruction_snapshot(
            run_uuid,
            {},
            {},
            {},
            snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_CURRENT,
        )
        if updated_run is None:
            raise RuntimeError(
                f"Run {run_id_str} not found while writing empty instruction snapshot"
            )
        return {}

    registry = YAMLRegistry.get_instance()
    version_repo = DocumentTypeInstructionVersionRepository(session)
    override_service = InstructionOverrideService(session)

    versions: dict[str, str] = {}
    manifest: dict[str, dict[str, Any]] = {}
    payload: dict[str, dict[str, Any]] = {}
    resolution_errors: list[dict[str, str]] = []

    for doc_type in sorted(unique_doc_types):
        try:
            entry = await _resolve_snapshot_entry(
                doc_type=doc_type,
                tenant_id=tenant_id,
                deal_id=deal_id,
                registry=registry,
                version_repo=version_repo,
                override_service=override_service,
                compiler=compiler,
                run_id=run_id_str,
            )

            versions[doc_type] = entry.version_id
            manifest[doc_type] = entry.manifest_entry
            payload[doc_type] = entry.payload

            logger.info(
                "freeze_instruction_snapshot: instruction entry resolved",
                run_id=run_id_str,
                doc_type=doc_type,
                version_id=entry.version_id,
                resolution_strategy=entry.manifest_entry.get("resolution_strategy"),
                override_id=entry.manifest_entry.get("override_id"),
                tenant_override_id=entry.manifest_entry.get("tenant_override_id"),
                deal_override_id=entry.manifest_entry.get("deal_override_id"),
                is_overridden=entry.manifest_entry.get("is_overridden", False),
            )

        except Exception as resolve_exc:
            resolution_errors.append(
                {
                    "doc_type": doc_type,
                    "error_type": type(resolve_exc).__name__,
                    "message": str(resolve_exc),
                }
            )
            logger.exception(
                "freeze_instruction_snapshot: failed to resolve snapshot entry",
                run_id=run_id_str,
                doc_type=doc_type,
                tenant_id=str(tenant_id) if tenant_id else None,
                deal_id=str(deal_id) if deal_id else None,
                error=str(resolve_exc),
                error_type=type(resolve_exc).__name__,
            )

    if resolution_errors:
        logger.error(
            "freeze_instruction_snapshot: refusing to persist partial strict snapshot",
            run_id=run_id_str,
            failed_doc_types_count=len(resolution_errors),
            failed_doc_types=[item["doc_type"] for item in resolution_errors[:20]],
        )
        raise InstructionSnapshotFreezeError(
            run_id=run_id_str,
            errors=resolution_errors,
        )

    updated_run = await run_repo.update_instruction_snapshot(
        run_uuid,
        versions,
        manifest,
        payload,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_CURRENT,
    )
    if updated_run is None:
        raise RuntimeError(
            f"Run {run_id_str} not found while writing instruction snapshot"
        )

    logger.info(
        "freeze_instruction_snapshot: completed",
        run_id=run_id_str,
        tenant_id=str(tenant_id) if tenant_id else None,
        deal_id=str(deal_id) if deal_id else None,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_CURRENT,
        fixed_count=len(versions),
        fixed_doc_types=sorted(versions.keys())[:20],
    )

    return versions


def build_doc_type_loader(run_snap: RunSnapshot) -> DocTypeCheckLoader:
    """
    Построить DocTypeCheckLoader для исполнения checks в рамках Run.

    Strict mode (snapshot_schema_version >= 1):
    - payload обязателен;
    - filesystem fallback ЗАПРЕЩЁН;
    - используется frozen effective payload из Run snapshot.

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