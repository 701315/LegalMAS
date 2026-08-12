# src/engine/checks/planning/planner.py

"""
Планирование проверок: выбор checks для документа или сегмента
по doc_type / segment_doc_type, триггерам и режиму.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger
from core.pipeline_snapshots import DocumentSnapshot, snapshot_document
from db.repositories.document_repo import DocumentRepository
from engine.doc_type_checks.loader import DocTypeCheckLoader

from .context import CheckContext

logger = get_logger(__name__)

# Мягкие лимиты
MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50


def _to_uuid(val: Any) -> uuid.UUID:
    """
    Безопасно конвертирует значение в uuid.UUID с понятной ошибкой.

    Для непрофессионального программиста:
    - Если val уже uuid.UUID — просто возвращаем его.
    - Если val — строка или другой тип, пробуем привести к строке и распарсить как UUID.
    - Если не получилось — падаем с ValueError с пояснением, что именно было не так.
    """
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (TypeError, ValueError, AttributeError) as e:
        raise ValueError(
            f"CheckPlanner: cannot convert {val!r} (type={type(val).__name__}) to UUID"
        ) from e


def _normalize_triggers(raw: Any) -> list[str]:
    """
    Нормализует сырой список триггеров в list[str].

    Для непрофессионального программиста:
    - Если raw — список/кортеж и т.п. → берём только строковые элементы.
    - Если raw — строка или вообще не итерируемый объект → возвращаем пустой список.
    """
    if isinstance(raw, Iterable) and not isinstance(raw, str | bytes):
        return [t for t in raw if isinstance(t, str)]
    return []

def _normalize_confidence_zone(raw: Any) -> str | None:
    """
    Нормализовать confidence_zone в одно из:
    - confident
    - low
    - unknown

    Любое другое значение -> None
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"confident", "low", "unknown"}:
        return text
    return None


def _derive_confidence_zone_from_confidence(confidence: float | None) -> tuple[str | None, bool]:
    """
    Вывести confidence zone из числовой confidence, если зона не пришла явно.

    Использует те же пороги что и ResultBuilder:
    - confident  : >= CLASSIFICATION_HYBRID_ACCEPT
    - unknown    : <= CLASSIFICATION_UNKNOWN_MAX
    - low        : между ними

    Возвращает:
    - zone_name
    - requires_manual_review
    """
    if confidence is None:
        return None, False

    hybrid_accept = float(getattr(settings, "CLASSIFICATION_HYBRID_ACCEPT", 0.45))
    unknown_max = float(getattr(settings, "CLASSIFICATION_UNKNOWN_MAX", 0.40))

    if confidence >= hybrid_accept:
        return "confident", False
    if confidence <= unknown_max:
        return "unknown", True
    return "low", True


class CheckPlanner:
    """
    Выбирает и фильтрует checks по текущему режиму
    (global_only / doc_type_only / global_and_doc_type),
    используя единый контракт CheckContext.

    Для непрофессионального программиста:
    - Planner больше не читает поля doc напрямую.
    - Он работает с CheckContext, где уже собран профиль
      документа или сегмента (тип, триггеры, scope).
    """

    def __init__(
        self,
        checks_mode: str = "global_and_doc_type",
        doc_type_loader: DocTypeCheckLoader | None = None,
    ):
        self.checks_mode = checks_mode
        # В режиме execution/review лоадер должен быть инициализирован 
        # правильным DatabaseProvider'ом извне (из CheckRunner или ReviewService)
        self.doc_type_loader = doc_type_loader or DocTypeCheckLoader()

    # ── Вспомогательные методы для построения контекста ────────────

    def build_context_for_document(
        self,
        doc,
        document_version_id: uuid.UUID | None,
    ) -> CheckContext:
        """
        Построить CheckContext для документа (scope="document").

        Принимает любой duck-typed объект с полями:
        - id
        - doc_type / doctype
        - applicable_triggers
        - classification_confidence (если есть)
        - classification_confidence_zone (если есть)
        - classification_requires_manual_review (если есть)

        Если classification_confidence_zone не передан явно, planner сам
        выводит его из classification_confidence по тем же порогам,
        что и классификатор.
        """
        raw_doc_type = (
            getattr(doc, "doc_type", None)
            or getattr(doc, "doctype", None)
            or ""
        )
        raw_triggers = getattr(doc, "applicable_triggers", None) or []
        trigger_list = _normalize_triggers(raw_triggers)

        raw_confidence = getattr(doc, "classification_confidence", None)
        try:
            classification_confidence = (
                float(raw_confidence) if raw_confidence is not None else None
            )
        except (TypeError, ValueError):
            classification_confidence = None

        explicit_zone = _normalize_confidence_zone(
            getattr(doc, "classification_confidence_zone", None)
        )
        if explicit_zone is None:
            derived_zone, derived_requires_review = _derive_confidence_zone_from_confidence(
                classification_confidence
            )
        else:
            derived_zone = explicit_zone
            derived_requires_review = explicit_zone != "confident"

        explicit_requires_review = bool(
            getattr(doc, "classification_requires_manual_review", False)
        )

        return CheckContext(
            scope="document",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=document_version_id,
            document_type=raw_doc_type or None,
            classification_confidence=classification_confidence,
            classification_confidence_zone=derived_zone,
            classification_requires_manual_review=(
                explicit_requires_review or derived_requires_review
            ),
            segment_id=None,
            segment_doc_type=None,
            triggers=frozenset(trigger_list),
        )

    def build_context_for_segment(
        self,
        *,
        doc,
        document_version_id: uuid.UUID,
        segment_info,
    ) -> CheckContext:
        """
        Построить CheckContext для сегмента (scope="segment").

        segment_info должен иметь поля:
        - segment_id
        - segment_doc_type
        - triggers
        - classification_confidence (optional)
        - classification_confidence_zone (optional)
        - classification_requires_manual_review (optional)

        Если зона не передана — выводим её из classification_confidence.
        """
        raw_triggers = getattr(segment_info, "triggers", None) or []
        trigger_list = _normalize_triggers(raw_triggers)

        seg_doc_type = getattr(segment_info, "segment_doc_type", None)

        raw_confidence = getattr(segment_info, "classification_confidence", None)
        try:
            classification_confidence = (
                float(raw_confidence) if raw_confidence is not None else None
            )
        except (TypeError, ValueError):
            classification_confidence = None

        explicit_zone = _normalize_confidence_zone(
            getattr(segment_info, "classification_confidence_zone", None)
        )
        if explicit_zone is None:
            derived_zone, derived_requires_review = _derive_confidence_zone_from_confidence(
                classification_confidence
            )
        else:
            derived_zone = explicit_zone
            derived_requires_review = explicit_zone != "confident"

        explicit_requires_review = bool(
            getattr(segment_info, "classification_requires_manual_review", False)
        )

        return CheckContext(
            scope="segment",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=document_version_id,
            document_type=None,  # для сегмента используем segment_doc_type
            classification_confidence=classification_confidence,
            classification_confidence_zone=derived_zone,
            classification_requires_manual_review=(
                explicit_requires_review or derived_requires_review
            ),
            segment_id=getattr(segment_info, "segment_id", None),
            segment_doc_type=seg_doc_type or None,
            triggers=frozenset(trigger_list),
        )

    # ── Новый основной API: по контексту ───────────────────────────

    def select_checks_for_context(
        self,
        ctx: CheckContext,
        playbook,
    ) -> tuple[list[Any], str, str | None, list[str], list[Any], list[Any]]:
        """
        Подобрать checks для заданного CheckContext.

        Возвращает:
        - checks — итоговый дедуплицированный список
        - mode — использованный режим (global_only / doc_type_only / global_and_doc_type)
        - effective_doc_type — doc_type, по которому реально подбирались checks
          (для scope="segment" это segment_doc_type)
        - triggers — список применимых триггеров из контекста
        - global_checks — чеки из playbook
        - doc_type_checks — чеки из YAML doc-type

        Новое поведение:
        - при classification_confidence_zone == "low" planner добавляет
          generic fallback checks из playbook.get_conditional_checks("", triggers),
          чтобы уменьшить риск неверного чеклиста при шаткой классификации.
        """
        triggers = sorted(ctx.triggers)

        # Выбираем "эффективный" doc_type: для segment берём segment_doc_type
        if ctx.scope == "segment":
            effective_doc_type = ctx.segment_doc_type
        else:
            effective_doc_type = ctx.document_type

        if not effective_doc_type:
            # Если нет типа, то doc_type-специфические чеки не подтянутся
            global_checks = playbook.get_conditional_checks("", triggers)
            doc_type_checks: list[Any] = []
        else:
            global_checks = playbook.get_conditional_checks(effective_doc_type, triggers)
            doc_type_checks = self.doc_type_loader.load_checks_for_doc(
                doc_type=effective_doc_type,
                applicable_triggers=triggers,
            )

        # Если классификация low-confidence — добавляем generic fallback checks.
        # Это не отменяет основной doc_type, а расширяет чеклист для safety-net.
        # Дубликаты будут сняты ниже по check_id.
        generic_fallback_checks: list[Any] = []
        if ctx.is_low_confidence_classification:
            try:
                generic_fallback_checks = playbook.get_conditional_checks("", triggers)
                logger.info(
                    "CheckPlanner: adding generic fallback checks due to low-confidence classification",
                    extra={
                        "document_id": str(ctx.document_id),
                        "scope": ctx.scope,
                        "effective_doc_type": effective_doc_type,
                        "classification_confidence": ctx.classification_confidence,
                        "classification_confidence_zone": ctx.classification_confidence_zone,
                        "generic_fallback_checks": len(generic_fallback_checks),
                    },
                )
            except Exception as e:
                logger.warning(
                    "CheckPlanner: failed to load generic fallback checks",
                    extra={
                        "document_id": str(ctx.document_id),
                        "scope": ctx.scope,
                        "error": str(e),
                    },
                )
                generic_fallback_checks = []

        mode = self.checks_mode
        if mode == "global_only":
            raw_checks = global_checks + generic_fallback_checks
        elif mode == "doc_type_only":
            raw_checks = doc_type_checks + generic_fallback_checks
        else:
            raw_checks = global_checks + doc_type_checks + generic_fallback_checks

        seen_ids: set[str] = set()
        checks: list[Any] = []
        for check in raw_checks:
            check_id = str(getattr(check, "id", "")) or ""
            if not check_id or check_id in seen_ids:
                continue
            seen_ids.add(check_id)
            checks.append(check)

        return (
            checks,
            mode,
            effective_doc_type,
            triggers,
            global_checks,
            doc_type_checks,
        )

    def find_check_for_context(
        self,
        ctx: CheckContext,
        playbook,
        check_id: str,
    ):
        """
        Найти конкретный check по check_id среди checks,
        которые применимы к данному контексту (document или segment).
        """
        (
            checks,
            mode,
            effective_doc_type,
            triggers,
            global_checks,
            doc_type_checks,
        ) = self.select_checks_for_context(ctx, playbook)

        target_check_id = str(check_id)

        for check in checks:
            current_check_id = str(getattr(check, "id", ""))
            if current_check_id == target_check_id:
                return check

        logger.warning(
            "CheckPlanner: target check not applicable for context",
            extra={
                "document_id": str(ctx.document_id),
                "document_version_id": str(ctx.document_version_id)
                if ctx.document_version_id
                else None,
                "scope": ctx.scope,
                "segment_id": ctx.segment_id,
                "segment_doc_type": ctx.segment_doc_type,
                "doc_type": effective_doc_type,
                "check_id": target_check_id,
                "checks_mode": mode,
                "triggers": triggers,
                "global_checks": len(global_checks),
                "doc_type_checks": len(doc_type_checks),
                "total_checks": len(checks),
            },
        )
        return None

    # ── Legacy-обёртки для совместимости ──────────────────────────

    def get_document_profile(self, doc) -> tuple[str, list[str]]:
        """
        Legacy helper. Оставлен для обратной совместимости.

        Принимает любой duck-typed объект с полями doc_type / applicable_triggers:
        - ORM Document,
        - DocumentSnapshot из core.pipeline_snapshots.

        Новый код должен использовать build_context_for_document.
        """
        raw_doc_type = (
            getattr(doc, "doc_type", None)
            or getattr(doc, "doctype", None)
            or ""
        )
        raw_triggers = getattr(doc, "applicable_triggers", None) or []
        applicable_triggers = _normalize_triggers(raw_triggers)

        return raw_doc_type, applicable_triggers

    def select_checks_for_document(
        self,
        doc,
        playbook,
    ) -> tuple[list[Any], str, str, list[str], list[Any], list[Any]]:
        """
        Legacy API для document-level. Сохраняем сигнатуру 1:1.

        Принимает любой duck-typed объект (ORM или DocumentSnapshot).
        Внутри просто строим document-context и делегируем в select_checks_for_context.
        """
        doc_type, applicable_triggers = self.get_document_profile(doc)
        ctx = self.build_context_for_document(doc, None)

        checks, mode, effective_doc_type, triggers, global_checks, doc_type_checks = (
            self.select_checks_for_context(ctx, playbook)
        )

        # Для совместимости возвращаем legacy doc_type (из doc), а не effective_doc_type.
        return (
            checks,
            mode,
            doc_type,
            applicable_triggers,
            global_checks,
            doc_type_checks,
        )

    def find_check_for_document(
        self,
        doc,
        playbook,
        check_id: str,
    ):
        """
        Legacy API. Сохраняет поведение find_check_for_document через document-context.

        Принимает любой duck-typed объект (ORM или DocumentSnapshot).
        """
        ctx = self.build_context_for_document(doc, None)
        return self.find_check_for_context(ctx, playbook, check_id)

    # ── Planning для Run (пока только document-level) ──────────────

    async def plan_checks_for_run(
        self,
        *,
        session: AsyncSession,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
        playbook,
    ) -> dict[str, Any]:
        """
        Только спланировать checks для Run, без выполнения LLM.

        Пока планирование остаётся document-level (scope="document"),
        но внутри уже используется CheckContext.

        Важно про snapshot:
        - После загрузки docs сразу снимаем DocumentSnapshot из core.pipeline_snapshots.
        - Цикл планирования работает только со snapshot-данными.
        - Это предотвращает случайное обращение к ORM-атрибутам
          после await-границы в будущих изменениях метода.

        ИЗМЕНЕНО (Instruction Versioning):
        - Каждый элемент pairs теперь содержит дополнительное поле "doc_type".
        - Это позволяет worker фиксировать instruction versions без повторного
          запроса к БД для получения doc_type.
        """
        processed_docs = 0
        total_checks = 0
        errors = 0
        pairs: list[dict[str, Any]] = []

        doc_repo = DocumentRepository(session)
        docs = await doc_repo.list_by_deal_id(deal_id)

        if len(docs) > MAX_DOCS_PER_RUN:
            logger.warning(
                "CheckPlanner: too many documents for run planning, truncating",
                extra={
                    "deal_id": str(deal_id),
                    "run_id": str(run_id),
                    "docs_found": len(docs),
                    "max_docs": MAX_DOCS_PER_RUN,
                },
            )
            docs = docs[:MAX_DOCS_PER_RUN]

        # Снимаем DocumentSnapshot сразу после загрузки ORM-объектов
        # через shared контракт core.pipeline_snapshots.
        # Цикл планирования не делает await, но snapshot защищает
        # от будущих добавлений await в этот метод.
        doc_snaps: list[DocumentSnapshot] = [snapshot_document(doc) for doc in docs]

        for doc_snap in doc_snaps:
            try:
                doc_type, applicable_triggers = self.get_document_profile(doc_snap)
                ctx = self.build_context_for_document(doc_snap, None)

                (
                    checks,
                    mode,
                    effective_doc_type,
                    triggers,
                    global_checks,
                    doc_type_checks,
                ) = self.select_checks_for_context(ctx, playbook)

                logger.info(
                    "CheckPlanner: planned checks for document",
                    extra={
                        "doc_id": doc_snap.document_id_str,
                        "deal_id": str(deal_id),
                        "run_id": str(run_id),
                        "scope": ctx.scope,
                        "doc_type": effective_doc_type,
                        "triggers": triggers,
                        "checks_mode": mode,
                        "global_checks": len(global_checks),
                        "doc_type_checks": len(doc_type_checks),
                        "total_checks": len(checks),
                    },
                )

                for check in checks:
                    check_id = getattr(check, "id", None)
                    if not check_id:
                        continue
                    
                    # ИЗМЕНЕНО: добавлено поле "doc_type" для фиксации instruction versions
                    # в worker без дополнительного SQL-запроса.
                    pairs.append({
                        "doc_id": doc_snap.document_id_str,
                        "check_id": str(check_id),
                        "doc_type": effective_doc_type,
                    })
                    total_checks += 1

                processed_docs += 1

            except Exception as e:
                errors += 1
                logger.exception(
                    "CheckPlanner: failed to plan checks for document",
                    extra={
                        "doc_id": doc_snap.document_id_str,
                        "deal_id": str(deal_id),
                        "run_id": str(run_id),
                        "error": str(e),
                    },
                )
                if errors >= MAX_ERRORS_PER_RUN:
                    logger.error(
                        "CheckPlanner: too many errors during planning, stopping",
                        extra={
                            "deal_id": str(deal_id),
                            "run_id": str(run_id),
                            "errors": errors,
                        },
                    )
                    break

        return {
            "pairs": pairs,
            "processed_docs": processed_docs,
            "total_checks": total_checks,
            "errors": errors,
        }
    

    