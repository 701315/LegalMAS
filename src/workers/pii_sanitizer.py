"""
PII Sanitizer Worker.

Пайплайн: extract → pii → structure → classify → run_deal_checks.

В V2-пайплайне (DOCUMENT_LAYOUT_V2_ENABLED = True):
- Считывает входящий layout_primary_ref из run-scoped таблицы резолва языков.
- Записывает sanitized-layout в document_run_language_resolution.layout_primary_sanitized_ref
  И дублирует в DocumentVersion (для обратной совместимости с downstream-стадиями).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from classifiers.yaml_registry import YAMLRegistry
from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError
from core.logging import get_logger
from core.stage_trace import build_stage_trace_fragment
from services.document_layout.config import layout_config
from db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
)
from db.repositories.document_run_language_resolution_repo import (
    DocumentRunLanguageResolutionRepository,
)
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.pii_detector import get_pii_detector, get_preserve_types
from services.pii_encryption import PIIEncryptionError, get_pii_encryptor
from services.pii_tokenizer import PIIPolicy, PIITokenizer
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


class PIISanitizer:
    def __init__(
        self,
        uow: UnitOfWork,
        artifact_store,
        artifact_tenant_id: uuid.UUID | str,
        detector=None,
        tokenizer=None,
        encryptor=None,
        run_id: str | None = None,
    ):
        self.uow = uow
        self.store = artifact_store
        self.artifact_tenant_id: str = str(artifact_tenant_id)
        self.run_id = run_id

        self.doc_repo = DocumentRepository(uow.session)
        self.version_repo = DocumentVersionRepository(uow.session)
        self.res_repo = DocumentRunLanguageResolutionRepository(uow.session)
        self.audit_repo = AuditRepository(uow.session)

        self.detector = detector or get_pii_detector()
        self.tokenizer = tokenizer or PIITokenizer()
        self.encryptor = encryptor or get_pii_encryptor()

    async def sanitize(self, document_version_id: uuid.UUID) -> dict[str, Any]:
        version = await self.version_repo.get_by_id(document_version_id)
        if not version:
            raise PermanentError(f"DocumentVersion {document_version_id} not found")

        doc = await self.doc_repo.get_by_id(version.document_id)
        if not doc:
            raise PermanentError(f"Document {version.document_id} not found")

        if self._should_skip(doc):
            logger.info("Document already sanitized, skipping", document_id=str(doc.id))
            _skip_trace = build_stage_trace_fragment(
                strategy="trigger_and_policy_based",
                input_summary={"document_id": str(doc.id), "skip_reason": "already_sanitized"},
                output_summary={},
                warnings=["skipped_already_sanitized"],
                artifact_refs={},
                decision_details=None,
            )
            return {
                "document_id": str(doc.id),
                "skipped": True,
                "stage_execution_trace_status": "skipped",
                "stage_execution_result_details": _skip_trace,
            }

        v2_enabled = getattr(settings, "DOCUMENT_LAYOUT_V2_ENABLED", False) or layout_config.document_layout_v2_enabled
        run_uuid = uuid.UUID(self.run_id) if self.run_id else None

        layout_ref = None
        res_record = None

        if v2_enabled and run_uuid:
            res_record = await self.res_repo.get_by_run_and_version(run_uuid, document_version_id)
            if res_record:
                layout_ref = res_record.layout_primary_ref

        if not layout_ref:
            layout_ref = getattr(version, "layout_primary_ref", None)

        if not layout_ref:
            raise PermanentError(f"layout_primary_ref is required for PII sanitization, version={document_version_id}")

        try:
            layout_raw = self.store.get_json(layout_ref)
            elements = layout_raw.get("elements", [])

            triggers = getattr(doc, "applicable_triggers", None) or []
            policy = self._build_policy(doc, triggers)

            sanitized_elements, global_mapping, stats = self._process_elements(elements, policy)

            layout_sanitized = {**layout_raw, "elements": sanitized_elements}
            
            if v2_enabled and run_uuid:
                sanitized_path = ArtifactPath.run_layout_primary_sanitized(
                    tenant_id=self.artifact_tenant_id,
                    deal_id=str(doc.deal_id),
                    run_id=self.run_id,
                    document_id=str(doc.id),
                )
            else:
                sanitized_path = self._build_sanitized_path(doc, self.artifact_tenant_id)

            # Сохраняем возвращаемую S3-ссылку макета (а не относительный путь)
            layout_primary_sanitized_ref = self.store.put_json(sanitized_path, layout_sanitized)

            mapping_path = self._build_mapping_path(doc, self.artifact_tenant_id)
            encrypted = self.encryptor.encrypt_mapping(global_mapping)
            
            # Сохраняем возвращаемую S3-ссылку маппинга
            pii_mapping_ref = self.store.put_file(mapping_path, encrypted)

            # Обновляем резолв-таблицу в V2
            if v2_enabled and res_record:
                res_record.layout_primary_sanitized_ref = layout_primary_sanitized_ref
                res_record.resolution_status = "LANGUAGE_READY"

            # Дублируем ссылки в DocumentVersion для 100% совместимости с downstream
            await self.version_repo.update_refs(
                version_id=version.id,
                layout_primary_sanitized_ref=layout_primary_sanitized_ref,
                pii_mapping_ref=pii_mapping_ref,
            )

            await self.doc_repo.update_status(
                doc_id=doc.id,
                status=DocumentStatus.SANITIZED.value,
                processing_error_details=None,
            )

            if settings.PII_AUDIT_ENABLED:
                await self._write_audit_log(doc, triggers, policy, stats)

            logger.info(
                "PII sanitization complete",
                document_id=str(doc.id),
                entities_detected=stats["detected"],
                entities_tokenized=stats["tokenized"],
                entities_preserved=stats["preserved"],
            )

            _trace = build_stage_trace_fragment(
                strategy="trigger_and_policy_based",
                input_summary={
                    "document_id": str(doc.id),
                    "layout_source": "layout_primary_ref",
                    "doc_type": getattr(doc, "doc_type", None),
                    "triggers_count": len(triggers),
                },
                output_summary={
                    "entities_detected": stats["detected"],
                    "entities_tokenized": stats["tokenized"],
                    "entities_preserved": stats["preserved"],
                },
                warnings=[],
                artifact_refs={
                    "layout_primary_sanitized_ref": layout_primary_sanitized_ref,
                    "pii_mapping_ref": pii_mapping_ref,
                },
                decision_details={
                    "encryption_enabled": self.encryptor.is_encryption_enabled,
                },
            )

            return {
                "status": DocumentStatus.SANITIZED.value,
                "document_id": str(doc.id),
                "entities_detected": stats["detected"],
                "entities_tokenized": stats["tokenized"],
                "entities_preserved": stats["preserved"],
                "tenant_id": self.artifact_tenant_id,
                "skipped": False,
                "committed": True,
                "stage_execution_result_details": _trace,
            }

        except PIIEncryptionError as e:
            raise QuarantineError(
                f"Encryption error: {e}",
                document_id=str(doc.id),
                reason="pii_encryption_error",
            ) from e

    def _should_skip(self, doc) -> bool:
        if not settings.PII_SKIP_IF_ALREADY_SANITIZED:
            return False
        return doc.status == DocumentStatus.SANITIZED.value

    def _build_policy(self, doc, triggers: list) -> PIIPolicy:
        party_role_keywords: dict[str, str] | None = None
        type_code = getattr(doc, "doc_type", None)

        if type_code:
            try:
                registry = YAMLRegistry.get_instance()
                cfg = registry.get_config(type_code)
                if cfg and cfg.party_role_keywords:
                    party_role_keywords = cfg.party_role_keywords
            except Exception as e:
                logger.warning("Failed to load YAML config for doc_type", doc_type=type_code, error=str(e))

        return PIITokenizer.build_policy_from_triggers(
            applicable_triggers=triggers,
            party_role_keywords=party_role_keywords,
        )

    def _process_elements(
        self,
        elements: list[dict],
        policy: PIIPolicy,
    ) -> tuple[list[dict], dict[str, str], dict[str, int]]:
        sanitized_elements = []
        global_mapping: dict[str, str] = {}
        stats = {"detected": 0, "tokenized": 0, "preserved": 0, "role_mapped": 0}

        preserve_types = get_preserve_types()
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        for elem in elements:
            raw_text = elem.get("text", "")
            if not raw_text:
                sanitized_elements.append(elem)
                continue

            all_entities = self.detector.detect(raw_text)
            stats["detected"] += len(all_entities)

            pii_entities = [e for e in all_entities if e.type not in preserve_types]

            if not pii_entities:
                sanitized_elements.append({**elem})
                stats["preserved"] += len(all_entities)
                continue

            context = raw_text[:500]
            result = self.tokenizer.tokenize(
                raw_text,
                pii_entities,
                policy,
                context_window=context,
                value_to_token=value_to_token,
                counters=doc_counters,
            )

            global_mapping.update(result.mapping)
            stats["tokenized"] += result.entities_tokenized
            stats["preserved"] += result.entities_preserved
            stats["role_mapped"] += result.entities_role_mapped

            sanitized_elements.append({**elem, "text": result.sanitized_text})

        return sanitized_elements, global_mapping, stats

    def _build_sanitized_path(self, doc, tenant_id: str) -> str:
        deal_id = str(doc.deal_id)
        return ArtifactPath.layout_primary_sanitized(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
        )

    def _build_mapping_path(self, doc, tenant_id: str) -> str:
        deal_id = str(doc.deal_id)
        return ArtifactPath.pii_mapping(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
        )

    async def _write_audit_log(
        self,
        doc,
        triggers: list,
        policy: PIIPolicy,
        stats: dict,
    ) -> None:
        await self.audit_repo.log(
            tenant_id=uuid.UUID(self.artifact_tenant_id),
            deal_id=doc.deal_id,
            action="SANITIZE",
            actor="system:pii_sanitizer",
            actor_role="system",
            details={
                "document_id": str(doc.id),
                "entities_detected": stats["detected"],
                "entities_tokenized": stats["tokenized"],
                "entities_preserved": stats["preserved"],
                "entities_role_mapped": stats["role_mapped"],
                "classification_level": getattr(doc, "classification_level", None),
                "applicable_triggers": triggers,
                "role_map_used": policy.use_role_map,
                "yaml_keywords_used": policy.party_role_keywords is not None,
                "encryption_enabled": self.encryptor.is_encryption_enabled,
            },
        )


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="pii.sanitize_document",
    track_job=False,
    queue="default",
)
def sanitize_document(
    self,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
    **kwargs,
) -> dict:
    version_uuid = uuid.UUID(document_version_id)
    document_id = kwargs.get("document_id")

    async def _run() -> dict:
        async with db_uow() as uow_main:
            resolved_tenant_id = await resolve_artifact_tenant_id(
                session=uow_main.session,
                deal_id=deal_id,
                document_id=document_id,
                payload_tenant_id=tenant_id,
            )

            store = ArtifactStore(settings)
            sanitizer = PIISanitizer(
                uow=uow_main,
                artifact_store=store,
                artifact_tenant_id=resolved_tenant_id,
                run_id=run_id,
            )
            try:
                result = await sanitizer.sanitize(version_uuid)
                return result

            except PermanentError as e:
                async with db_uow() as uow_err:
                    failed_tenant_id = await resolve_artifact_tenant_id(
                        session=uow_err.session,
                        deal_id=deal_id,
                        document_id=document_id,
                        payload_tenant_id=resolved_tenant_id,
                    )
                    if stage_execution_id:
                        dse_err = DocumentStageExecutionRepository(uow_err.session)
                        await dse_err.mark_failed(
                            uuid.UUID(stage_execution_id),
                            error_details={
                                "stage": "pii",
                                "type": "permanent_error",
                                "reason": "pii_error",
                                "message": str(e),
                                "run_id": run_id,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )

                    await _mark_failed(
                        uow_err,
                        version_id=version_uuid,
                        tenant_id=str(failed_tenant_id),
                        message=str(e),
                    )
                return {"status": DocumentStatus.FAILED.value, "error": str(e)}

            except QuarantineError as e:
                async with db_uow() as uow_err:
                    failed_tenant_id = await resolve_artifact_tenant_id(
                        session=uow_err.session,
                        deal_id=deal_id,
                        document_id=document_id,
                        payload_tenant_id=resolved_tenant_id,
                    )
                    if stage_execution_id:
                        dse_err = DocumentStageExecutionRepository(uow_err.session)
                        await dse_err.mark_failed(
                            uuid.UUID(stage_execution_id),
                            error_details={
                                "stage": "pii",
                                "type": "quarantine_error",
                                "reason": getattr(e, "reason", "pii_quarantine"),
                                "message": str(e),
                                "run_id": run_id,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )

                    await _mark_quarantine(
                        uow_err,
                        version_id=version_uuid,
                        tenant_id=str(failed_tenant_id),
                        error=e,
                    )
                return {"status": DocumentStatus.QUARANTINE.value, "error": str(e)}

    from mas_queue.async_helpers import run_async
    result = run_async(_run())

    if run_id and result.get("committed") is True:
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
        )

    return result


async def _mark_failed(
    uow: UnitOfWork,
    version_id: uuid.UUID,
    *,
    tenant_id: str,
    message: str,
) -> None:
    version_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    version = await version_repo.get_by_id(version_id)
    if not version:
        return

    await doc_repo.set_failed(
        version.document_id,
        stage="pii",
        message=message,
        reason="pii_error",
        run_id=None,
    )

    document = await doc_repo.get_by_id(version.document_id)
    if not document:
        return

    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=document.deal_id,
            action="PII_SANITIZE_FAILED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document.id),
                "document_version_id": str(version_id),
                "stage": "pii",
                "reason": "pii_error",
                "message": message,
            },
        )
    except Exception:
        pass


async def _mark_quarantine(
    uow: UnitOfWork,
    version_id: uuid.UUID,
    *,
    tenant_id: str,
    error: QuarantineError,
) -> None:
    version_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    version = await version_repo.get_by_id(version_id)
    if not version:
        return

    reason = getattr(error, "reason", None)
    await doc_repo.set_quarantined(
        version.document_id,
        stage="pii",
        message=str(error),
        reason=reason,
        run_id=None,
    )

    document = await doc_repo.get_by_id(version.document_id)
    if not document:
        return

    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=document.deal_id,
            action="PII_SANITIZE_QUARANTINED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document.id),
                "document_version_id": str(version_id),
                "stage": "pii",
                "reason": reason,
                "message": str(error),
            },
        )
    except Exception:
        pass
