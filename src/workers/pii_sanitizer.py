"""
PII Sanitizer Worker.

Stage 5 в pipeline: extract → pii → structure → classify → run_checks

Архитектура (согласована с Stage 4):
  - Sync Celery task с async-обёрткой
  - UnitOfWork через db_uow() контекстный менеджер
  - Репозитории создаются с uow.session
  - Обработка ошибок: PermanentError → failed, QuarantineError → quarantine
"""

import asyncio
import uuid
from typing import Any

from celery import shared_task

from src.core.config import settings
from src.core.exceptions import PermanentError, QuarantineError
from src.core.logging import get_logger
from src.db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
)
from src.db.uow import UnitOfWork, db_uow
from src.services.pii_detector import get_pii_detector, get_preserve_types
from src.services.pii_encryption import PIIEncryptionError, get_pii_encryptor
from src.services.pii_tokenizer import PIIPolicy, PIITokenizer

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PII Sanitizer Service (async, testable)
# ═══════════════════════════════════════════════════════════════════════════════


class PIISanitizer:
    """
    Сервис санитизации PII в документе.

    Отделён от Celery-таски для тестируемости.
    Получает UoW извне (dependency injection).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        artifact_store,  # ArtifactStore
        detector=None,
        tokenizer=None,
        encryptor=None,
    ):
        self.uow = uow
        self.store = artifact_store

        # Репозитории создаём с сессией из UoW
        self.doc_repo = DocumentRepository(uow.session)
        self.version_repo = DocumentVersionRepository(uow.session)
        self.audit_repo = AuditRepository(uow.session)

        # Dependency injection для тестов
        self.detector = detector or get_pii_detector()
        self.tokenizer = tokenizer or PIITokenizer()
        self.encryptor = encryptor or get_pii_encryptor()

    async def sanitize(self, document_version_id: uuid.UUID) -> dict[str, Any]:
        """
        Выполнить санитизацию документа.

        Args:
            document_version_id: UUID версии документа

        Returns:
            dict с результатами: document_id, entities_*, skipped

        Raises:
            PermanentError: при неисправимых ошибках (документ не найден, нет raw текста)
            QuarantineError: при ошибках, требующих карантина (шифрование)
        """
        # 1. Загрузить версию и документ
        version = await self.version_repo.get_by_id(document_version_id)
        if not version:
            raise PermanentError(f"DocumentVersion {document_version_id} not found")

        doc = await self.doc_repo.get_by_id(version.document_id)
        if not doc:
            raise PermanentError(f"Document {version.document_id} not found")

        # 2. Идемпотентность
        if self._should_skip(doc):
            logger.info(
                "Document already sanitized, skipping",
                document_id=str(doc.id),
            )
            return {"document_id": str(doc.id), "skipped": True}

        # 3. Проверить наличие исходного текста
        if not version.text_layout_raw_ref:
            raise PermanentError(f"No text_layout_raw_ref for version {document_version_id}")

        try:
            # 4. Загрузить textlayoutraw из MinIO
            layout_raw = await self.store.get_json(version.text_layout_raw_ref)
            elements = layout_raw.get("elements", [])

            # 5. Построить PIIPolicy с учётом applicable_triggers и YAML-конфига
            triggers = getattr(doc, "applicable_triggers", None) or []
            policy = self._build_policy(doc, triggers)

            # 6. Обработать каждый элемент
            sanitized_elements, global_mapping, stats = self._process_elements(elements, policy)

            # 7. Сохранить textlayoutsanitized
            layout_sanitized = {**layout_raw, "elements": sanitized_elements}
            sanitized_path = self._build_sanitized_path(doc)
            await self.store.put_json(sanitized_path, layout_sanitized)

            # 8. Зашифровать и сохранить pii_mapping
            mapping_path = self._build_mapping_path(doc)
            encrypted = self.encryptor.encrypt_mapping(global_mapping)
            await self.store.put_file(mapping_path, encrypted)

            # 9. Обновить DocumentVersion и статус документа
            await self.version_repo.update_refs(
                version_id=version.id,
                sanitized_ref=sanitized_path,
            )
            await self.doc_repo.update_status(
                doc_id=doc.id,
                status="sanitized",
            )

            # 10. AuditLog
            if settings.PII_AUDIT_ENABLED:
                await self._write_audit_log(doc, triggers, policy, stats)

            logger.info(
                "PII sanitization complete",
                document_id=str(doc.id),
                entities_detected=stats["detected"],
                entities_tokenized=stats["tokenized"],
                entities_preserved=stats["preserved"],
                role_map_used=policy.use_role_map,
            )

            return {
                "document_id": str(doc.id),
                "entities_detected": stats["detected"],
                "entities_tokenized": stats["tokenized"],
                "entities_preserved": stats["preserved"],
                "skipped": False,
            }

        except PIIEncryptionError as e:
            raise QuarantineError(f"Encryption error: {e}") from e

    def _should_skip(self, doc) -> bool:
        """Проверить, нужно ли пропустить санитизацию (идемпотентность)."""
        if not settings.PII_SKIP_IF_ALREADY_SANITIZED:
            return False
        return doc.status == "sanitized"

    def _build_policy(self, doc, triggers: list) -> PIIPolicy:
        """
        Построить PIIPolicy с учётом YAML-конфига типа документа.

        Args:
            doc: Document model
            triggers: applicable_triggers из документа

        Returns:
            PIIPolicy с party_role_keywords из YAML (если доступен)
        """
        party_role_keywords: dict[str, str] | None = None

        # Пытаемся получить словарь ролей из YAML-реестра
        # ВАЖНО: на Stage 5 doc_type может быть ещё None (классификация позже)
        type_code = getattr(doc, "doc_type", None)

        if type_code:
            try:
                from src.classifiers.yaml_registry import YAMLRegistry

                registry = YAMLRegistry.get_instance()
                cfg = registry.get_config(type_code)

                if cfg and cfg.party_role_keywords:
                    party_role_keywords = cfg.party_role_keywords
                    logger.debug(
                        "Using party_role_keywords from YAML",
                        doc_type=type_code,
                        keywords_count=len(party_role_keywords),
                    )
            except Exception as e:
                logger.warning(
                    "Failed to load YAML config for doc_type",
                    doc_type=type_code,
                    error=str(e),
                )

        return PIITokenizer.build_policy_from_triggers(
            applicable_triggers=triggers,
            party_role_keywords=party_role_keywords,
        )

    def _process_elements(
        self,
        elements: list[dict],
        policy: PIIPolicy,
    ) -> tuple[list[dict], dict[str, str], dict[str, int]]:
        """
        Обработать элементы layout'а.

        Returns:
            (sanitized_elements, global_mapping, stats)
        """
        sanitized_elements = []
        global_mapping: dict[str, str] = {}
        stats = {"detected": 0, "tokenized": 0, "preserved": 0, "role_mapped": 0}

        # Получаем preserve_types один раз для всех элементов
        preserve_types = get_preserve_types()

        for elem in elements:
            raw_text = elem.get("text", "")
            if not raw_text:
                sanitized_elements.append(elem)
                continue

            # Детектируем PII
            all_entities = self.detector.detect(raw_text)
            stats["detected"] += len(all_entities)

            # Фильтруем preserve-типы для токенизации
            pii_entities = [e for e in all_entities if e.type not in preserve_types]

            if not pii_entities:
                sanitized_elements.append({**elem})
                stats["preserved"] += len(all_entities)
                continue

            # Токенизируем
            context = raw_text[:500]
            result = self.tokenizer.tokenize(raw_text, pii_entities, policy, context_window=context)

            global_mapping.update(result.mapping)
            stats["tokenized"] += result.entities_tokenized
            stats["preserved"] += result.entities_preserved
            stats["role_mapped"] += result.entities_role_mapped

            sanitized_elements.append({**elem, "text": result.sanitized_text})

        return sanitized_elements, global_mapping, stats

    def _build_sanitized_path(self, doc) -> str:
        """Построить путь для sanitized layout в MinIO."""
        tenant_id = "default"
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = str(doc.deal.tenant_id)

        deal_id = str(doc.deal_id)
        return f"tenants/{tenant_id}/deals/{deal_id}/sanitized/{doc.id}.json"

    def _build_mapping_path(self, doc) -> str:
        """Построить путь для PII mapping в MinIO."""
        tenant_id = "default"
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = str(doc.deal.tenant_id)

        deal_id = str(doc.deal_id)
        return f"tenants/{tenant_id}/deals/{deal_id}/pii/{doc.id}.bin"

    async def _write_audit_log(
        self,
        doc,
        triggers: list,
        policy: PIIPolicy,
        stats: dict,
    ) -> None:
        """Записать audit log."""
        tenant_id: uuid.UUID
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = doc.deal.tenant_id
        else:
            tenant_id = doc.deal_id

        await self.audit_repo.log(
            tenant_id=tenant_id,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Celery Task (sync wrapper → async execution)
# ═══════════════════════════════════════════════════════════════════════════════


@shared_task(
    name="pii.sanitize_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def sanitize_document(self, document_version_id: str) -> dict:
    """
    Celery-таска санитизации документа.

    Args:
        document_version_id: UUID версии документа (как строка от Celery)

    Sync wrapper для async-логики (паттерн Stage 4).
    """
    version_uuid = uuid.UUID(document_version_id)

    async def _run() -> dict:
        from src.storage.artifact_store import ArtifactStore

        async with db_uow() as uow:
            store = ArtifactStore(settings)
            sanitizer = PIISanitizer(uow=uow, artifact_store=store)

            try:
                result = await sanitizer.sanitize(version_uuid)

                # Запустить следующую стадию
                if not result.get("skipped") and not settings.DISABLE_DOWNSTREAM_TASKS:
                    from src.workers.structure_builder import build_structure

                    build_structure.delay(document_version_id=document_version_id)

                return result

            except PermanentError as e:
                logger.error(f"Permanent error for {document_version_id}: {e}")
                raise

            except QuarantineError as e:
                logger.error(f"Quarantine error for {document_version_id}: {e}")
                raise

    async def _run_with_error_handling() -> dict:
        try:
            return await _run()
        except PermanentError as e:
            await _mark_status(version_uuid, "failed")
            return {"status": "failed", "error": str(e)}
        except QuarantineError as e:
            await _mark_status(version_uuid, "quarantine")
            return {"status": "quarantine", "error": str(e)}

    async def _mark_status(version_id: uuid.UUID, status: str):
        async with db_uow() as uow:
            version_repo = DocumentVersionRepository(uow.session)
            doc_repo = DocumentRepository(uow.session)

            version = await version_repo.get_by_id(version_id)
            if version:
                await doc_repo.update_status(
                    doc_id=version.document_id,
                    status=status,
                )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_with_error_handling())
    finally:
        loop.close()
