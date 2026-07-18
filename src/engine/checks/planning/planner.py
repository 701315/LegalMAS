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

        Принимает любой duck-typed объект с полями id / doc_type / applicable_triggers:
        - ORM Document,
        - DocumentSnapshot из core.pipeline_snapshots.

        document_version_id можно получить заранее через
        DocumentVersionRepository.get_latest(doc.id).
        """
        raw_doc_type = getattr(doc, "doc_type", "") or ""
        raw_triggers = getattr(doc, "applicable_triggers", None) or []
        trigger_list = _normalize_triggers(raw_triggers)

        return CheckContext(
            scope="document",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=document_version_id,
            document_type=raw_doc_type or None,
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
        - triggers (list[str])
        Это идеально ложится на dataclass SegmentInfo.
        """
        raw_triggers = getattr(segment_info, "triggers", None) or []
        trigger_list = _normalize_triggers(raw_triggers)

        seg_doc_type = getattr(segment_info, "segment_doc_type", None)

        return CheckContext(
            scope="segment",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=document_version_id,
            document_type=None,  # для сегмента используем segment_doc_type
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

        mode = self.checks_mode
        if mode == "global_only":
            raw_checks = global_checks
        elif mode == "doc_type_only":
            raw_checks = doc_type_checks
        else:
            raw_checks = global_checks + doc_type_checks

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
        raw_doc_type = getattr(doc, "doc_type", "") or ""
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

        ctx = CheckContext(
            scope="document",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=None,
            document_type=doc_type or None,
            segment_id=None,
            segment_doc_type=None,
            triggers=frozenset(applicable_triggers),
        )

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
        doc_type, applicable_triggers = self.get_document_profile(doc)

        ctx = CheckContext(
            scope="document",
            document_id=_to_uuid(getattr(doc, "id", None)),
            document_version_id=None,
            document_type=doc_type or None,
            segment_id=None,
            segment_doc_type=None,
            triggers=frozenset(applicable_triggers),
        )

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
        pairs: list[dict[str, str]] = []

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

                ctx = CheckContext(
                    scope="document",
                    document_id=doc_snap.id,
                    document_version_id=None,
                    document_type=doc_type or None,
                    segment_id=None,
                    segment_doc_type=None,
                    triggers=frozenset(applicable_triggers),
                )

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
                        "doc_type": doc_type,  # ← НОВОЕ ПОЛЕ
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
    

    