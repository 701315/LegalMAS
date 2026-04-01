"""
PII Sanitizer Worker.

Пайплайн: extract → pii → structure → classify → run_deal_checks.

Назначение:
- Считать одноязычный макет документа (layout_primary) из MinIO.
- Найти PII‑сущности по политике (triggers + YAML‑конфиг типа документа).
- Заменить чувствительные данные токенами, зашифровать mapping и сохранить его.
- Сохранить sanitized‑layout и PII‑mapping в MinIO.
- Обновить статус документа: extracted -> sanitized.
- Запустить следующий этап пайплайна: workers.build_structure.

Архитектурные принципы:
- Celery‑таска синхронная (def) + async‑ядро (PIISanitizer.sanitize) под db_uow().
- Основная санитизация работает в одном UnitOfWork (db_uow) — читаем и пишем всё
  в рамках одной транзакции.
- Если при санитизации происходит ошибка, мы ОТДЕЛЬНО открываем новый db_uow
  только чтобы надёжно записать статус документа (FAILED / QUARANTINE) +
  processing_error_details.
- Для юриста это означает: документ никогда не «зависает» в промежуточном состоянии,
  всегда имеет честный и понятный статус.
"""

import uuid
from typing import Any

from core.config import settings
from core.exceptions import PermanentError, QuarantineError
from core.logging import get_logger
from db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
)
from db.uow import UnitOfWork, db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.pii_detector import get_pii_detector, get_preserve_types
from services.pii_encryption import PIIEncryptionError, get_pii_encryptor
from services.pii_tokenizer import PIIPolicy, PIITokenizer
from classifiers.yaml_registry import YAMLRegistry
from core.constants import DocumentStatus
from storage.artifact_store import ArtifactStore, ArtifactPath

logger = get_logger(__name__)


class PIISanitizer:
    """
    Сервис санитизации PII в документе.

    Отделён от Celery‑таски для тестируемости.
    Получает UnitOfWork извне, работает строго в его границах.
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

        # Репозитории поверх сессии из UoW
        self.doc_repo = DocumentRepository(uow.session)
        self.version_repo = DocumentVersionRepository(uow.session)
        self.audit_repo = AuditRepository(uow.session)

        # Dependency injection (для тестов)
        self.detector = detector or get_pii_detector()
        self.tokenizer = tokenizer or PIITokenizer()
        self.encryptor = encryptor or get_pii_encryptor()

    async def sanitize(self, document_version_id: uuid.UUID) -> dict[str, Any]:
        """
        Выполнить санитизацию документа.

        Возвращает словарь с полями:
        - document_id
        - entities_detected / tokenized / preserved
        - skipped (True, если документ уже был обработан)

        В этой функции мы НЕ открываем новый UnitOfWork,
        используем только тот, что был передан снаружи.
        """
        # 1. Загрузка версии и документа
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

        # 3. Выбор layout для санитизации.
        #
        # Цель: работать по одноязычному layout_primary, но при этом
        # не ломать старые версии, где его ещё нет.
        #
        # Новый приоритет (через модель DocumentVersion):
        # 1) layout_primary_ref (одноязычный layout из БД);
        # 2) text_layout_raw_ref (исторический multi‑lang layout);
        # 3) fallback по старому пути ArtifactPath.layout_primary(...) — только
        #    на случай, если поле в БД ещё не заполнено, но файл уже существует.
        layout_ref: str | None = None

        # tenant_id/deal_id берём так же, как в _build_sanitized_path
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = str(doc.deal.tenant_id)
        else:
            tenant_id = str(doc.deal_id)
        deal_id = str(doc.deal_id)

        # 3.1. Пробуем layout_primary_ref из БД
        if getattr(version, "layout_primary_ref", None):
            layout_ref = version.layout_primary_ref

        # 3.2. Если его нет — fallback на legacy raw layout
        elif getattr(version, "text_layout_raw_ref", None):
            layout_ref = version.text_layout_raw_ref

        # 3.3. Дополнительный fallback: старый путь ArtifactPath.layout_primary(...)
        # Используем только если по какой‑то причине поля в БД нет,
        # но файл в MinIO уже лежит по конвенционному пути.
        else:
            primary_path = ArtifactPath.layout_primary(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=str(doc.id),
            )
            if self.store.exists(primary_path):
                layout_ref = primary_path

        if not layout_ref:
            raise PermanentError(
                f"No layout_ref (primary or raw) for version {document_version_id}"
            )

        try:
            layout_raw = self.store.get_json(layout_ref)
            elements = layout_raw.get("elements", [])

            # 5. Построить PIIPolicy с учётом applicable_triggers и YAML‑конфига
            triggers = getattr(doc, "applicable_triggers", None) or []
            policy = self._build_policy(doc, triggers)

            # 6. Обработать элементы
            sanitized_elements, global_mapping, stats = self._process_elements(
                elements, policy
            )

            # 7. Сохранить sanitized‑layout
            #
            # В новой архитектуре для одноязычности мы хотим хранить
            # отдельный артефакт layout_primary_sanitized.
            # sanitized_path будет единственным источником истины для
            # layout_primary_sanitized_ref в DocumentVersion.
            layout_sanitized = {**layout_raw, "elements": sanitized_elements}
            sanitized_path = self._build_sanitized_path(doc)
            # ArtifactStore.put_json — синхронный метод, НЕ используем await
            self.store.put_json(sanitized_path, layout_sanitized)

            # 8. Зашифровать и сохранить pii_mapping
            mapping_path = self._build_mapping_path(doc)
            encrypted = self.encryptor.encrypt_mapping(global_mapping)
            # ArtifactStore.put_file — синхронный метод, НЕ используем await
            self.store.put_file(mapping_path, encrypted)

            # 9. Обновить DocumentVersion и статус документа
            #
            # ВАЖНО:
            # - sanitized_path указывает на одноязычный sanitized layout
            #   (ArtifactPath.layout_primary_sanitized).
            # - Через update_refs мы записываем эту ссылку в колонку
            #   layout_primary_sanitized_ref, которая должна быть основным
            #   источником истины для всех следующих стадий (structure,
            #   DocumentContentService, checks).
            await self.version_repo.update_refs(
                version_id=version.id,
                layout_primary_sanitized_ref=sanitized_path,
            )
            await self.doc_repo.update_status(
                doc_id=doc.id,
                status=DocumentStatus.SANITIZED.value,
                processing_error_details=None,
            )

            # 10. AuditLog (опционально)
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
            # Ошибка шифрования → карантин
            raise QuarantineError(
                f"Encryption error: {e}",
                document_id=str(doc.id),
                reason="pii_encryption_error",
            ) from e

    def _should_skip(self, doc) -> bool:
        """Проверить, нужно ли пропустить санитизацию (идемпотентность)."""
        if not settings.PII_SKIP_IF_ALREADY_SANITIZED:
            return False
        return doc.status == DocumentStatus.SANITIZED.value

    def _build_policy(self, doc, triggers: list) -> PIIPolicy:
        """
        Построить PIIPolicy с учётом YAML‑конфига типа документа.
        """
        party_role_keywords: dict[str, str] | None = None

        # На Stage 5 doc_type может быть ещё None (классификация позже)
        type_code = getattr(doc, "doc_type", None)

        if type_code:
            try:
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

        Возвращает:
          sanitized_elements, global_mapping, stats
        """
        sanitized_elements = []
        global_mapping: dict[str, str] = {}
        stats = {"detected": 0, "tokenized": 0, "preserved": 0, "role_mapped": 0}

        preserve_types = get_preserve_types()

        for elem in elements:
            raw_text = elem.get("text", "")
            if not raw_text:
                sanitized_elements.append(elem)
                continue

            # Детектируем PII
            all_entities = self.detector.detect(raw_text)
            stats["detected"] += len(all_entities)

            # Оставляем без токенизации типы, которые надо сохранить как есть
            pii_entities = [e for e in all_entities if e.type not in preserve_types]

            if not pii_entities:
                sanitized_elements.append({**elem})
                stats["preserved"] += len(all_entities)
                continue

            # Токенизируем
            context = raw_text[:500]
            result = self.tokenizer.tokenize(
                raw_text,
                pii_entities,
                policy,
                context_window=context,
            )

            global_mapping.update(result.mapping)
            stats["tokenized"] += result.entities_tokenized
            stats["preserved"] += result.entities_preserved
            stats["role_mapped"] += result.entities_role_mapped

            sanitized_elements.append({**elem, "text": result.sanitized_text})

        return sanitized_elements, global_mapping, stats

    def _build_sanitized_path(self, doc) -> str:
        """
        Построить путь для sanitized‑layout в MinIO через ArtifactPath.

        В новой архитектуре это будет одноязычный layout_primary_sanitized.
        """
        # tenant_id берём из связанной сделки, как единственный источник истины
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = str(doc.deal.tenant_id)
        else:
            # fallback для dev-режима, если связь не подгружена
            tenant_id = str(doc.deal_id)

        deal_id = str(doc.deal_id)
        return ArtifactPath.layout_primary_sanitized(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
        )

    def _build_mapping_path(self, doc) -> str:
        """Построить путь для PII‑mapping в MinIO через ArtifactPath."""
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id = str(doc.deal.tenant_id)
        else:
            tenant_id = str(doc.deal_id)

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
        """Записать audit‑лог по результатам санитизации."""
        if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
            tenant_id: uuid.UUID = doc.deal.tenant_id
        else:
            # fallback: используем deal_id как tenant_id (dev‑режим)
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
) -> dict:
    """
    Синхронная Celery‑таска санитизации документа.

    Внутри:
      - открывает основной UnitOfWork (uow_main) через db_uow();
      - запускает асинхронную санитизацию через PIISanitizer.sanitize;
      - при ошибке открывает второй, маленький UnitOfWork только для записи
        статуса (FAILED / QUARANTINE) + processing_error_details;
      - при успехе ставит задачу следующего этапа (Structure Builder).
    """
    version_uuid = uuid.UUID(document_version_id)

    async def _run() -> dict:
        # Основной UnitOfWork для санитизации
        async with db_uow() as uow_main:
            store = ArtifactStore(settings)
            sanitizer = PIISanitizer(uow=uow_main, artifact_store=store)

            try:
                result = await sanitizer.sanitize(version_uuid)

                # Успех → ставим следующую стадию (build_structure)
                if (
                    not result.get("skipped")
                    and not settings.DISABLE_DOWNSTREAM_TASKS
                ):
                    from mas_queue.celery_app import celery_app as _celery  # на случай циклов импорта

                    logger.info(
                        "Scheduling build_structure after PII",
                        document_version_id=document_version_id,
                    )

                    _celery.send_task(
                        "workers.build_structure",
                        kwargs={
                            "document_version_id": document_version_id,
                            # run_id можно добавить при необходимости
                        },
                    )

                return result

            except PermanentError as e:
                logger.error(
                    "Permanent error during PII sanitization",
                    document_version_id=document_version_id,
                    error=str(e),
                )
                # Отдельный UoW только для записи статуса FAILED + деталей
                async with db_uow() as uow_status:
                    await _mark_failed(
                        uow_status,
                        version_id=version_uuid,
                        message=str(e),
                    )
                return {
                    "status": DocumentStatus.FAILED.value,
                    "error": str(e),
                }

            except QuarantineError as e:
                logger.error(
                    "Quarantine error during PII sanitization",
                    document_version_id=document_version_id,
                    error=str(e),
                )
                # Отдельный UoW только для записи статуса QUARANTINE + деталей
                async with db_uow() as uow_status:
                    await _mark_quarantine(
                        uow_status,
                        version_id=version_uuid,
                        error=e,
                    )
                return {
                    "status": DocumentStatus.QUARANTINE.value,
                    "error": str(e),
                }

    # Переход в async‑мир через общий мост run_async
    return run_async(_run())


async def _mark_failed(
    uow: UnitOfWork,
    version_id: uuid.UUID,
    *,
    message: str,
) -> None:
    """
    Обновить статус документа на FAILED в отдельной, простой транзакции
    с заполнением processing_error_details.
    """
    version_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

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


async def _mark_quarantine(
    uow: UnitOfWork,
    version_id: uuid.UUID,
    *,
    error: QuarantineError,
) -> None:
    """
    Обновить статус документа на QUARANTINE в отдельной транзакции
    с заполнением processing_error_details.
    """
    version_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

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
    