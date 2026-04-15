# src/engine/checks/planning/planner.py

"""
Планирование проверок: выбор checks для документа по doc_type, триггерам и режиму.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from engine.doc_type_checks.loader import DocTypeCheckLoader

logger = get_logger(__name__)

# Мягкие лимиты
MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50


class CheckPlanner:
    """
    Выбирает и фильтрует checks для документа по текущему режиму
    (global_only / doc_type_only / global_and_doc_type).
    """

    def __init__(
        self,
        checks_mode: str = "global_and_doc_type",
        doc_type_loader: DocTypeCheckLoader | None = None,
    ):
        self.checks_mode = checks_mode
        self.doc_type_loader = doc_type_loader or DocTypeCheckLoader()

    def get_document_profile(self, doc) -> tuple[str, list[str]]:
        """
        Вернуть профиль документа: (doc_type, applicable_triggers).
        """
        doc_type = getattr(doc, "doc_type", "") or ""
        raw_triggers = getattr(doc, "applicable_triggers", None) or []

        if isinstance(raw_triggers, list):
            applicable_triggers = [t for t in raw_triggers if isinstance(t, str)]
        else:
            applicable_triggers = []

        return doc_type, applicable_triggers

    def select_checks_for_document(
        self,
        doc,
        playbook,
    ) -> tuple[list[Any], str, str, list[str], list[Any], list[Any]]:
        """
        Подобрать checks для документа по текущему checks_mode.

        Возвращает:
        - checks — итоговый дедуплицированный список
        - mode — использованный режим
        - doc_type
        - applicable_triggers
        - global_checks — чеки из playbook
        - doc_type_checks — чеки из YAML doc-type
        """
        doc_type, applicable_triggers = self.get_document_profile(doc)

        global_checks = playbook.get_conditional_checks(doc_type, applicable_triggers)
        doc_type_checks = self.doc_type_loader.load_checks_for_doc(
            doc_type=doc_type,
            applicable_triggers=applicable_triggers,
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
            check_id = str(getattr(check, "id", ""))
            if not check_id or check_id in seen_ids:
                continue
            seen_ids.add(check_id)
            checks.append(check)

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
        Найти конкретный check по check_id среди checks,
        которые реально применимы к данному документу.
        """
        (
            checks,
            mode,
            doc_type,
            applicable_triggers,
            global_checks,
            doc_type_checks,
        ) = self.select_checks_for_document(doc, playbook)

        target_check_id = str(check_id)

        for check in checks:
            current_check_id = str(getattr(check, "id", ""))
            if current_check_id == target_check_id:
                return check

        logger.warning(
            "CheckPlanner: target check not applicable for document",
            extra={
                "doc_id": str(getattr(doc, "id", None)),
                "deal_id": str(getattr(doc, "deal_id", "")),
                "doc_type": doc_type,
                "check_id": target_check_id,
                "checks_mode": mode,
                "applicable_triggers": applicable_triggers,
                "global_checks": len(global_checks),
                "doc_type_checks": len(doc_type_checks),
                "total_checks": len(checks),
            },
        )
        return None

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

        Возвращает:
        {
            "pairs": [{"doc_id": "...", "check_id": "..."}],
            "processed_docs": int,
            "total_checks": int,
            "errors": int,
        }
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

        for doc in docs:
            try:
                (
                    checks, mode, doc_type, applicable_triggers,
                    global_checks, doc_type_checks,
                ) = self.select_checks_for_document(doc, playbook)

                logger.info(
                    "CheckPlanner: planned checks for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
                        "run_id": str(run_id),
                        "doc_type": doc_type,
                        "triggers": applicable_triggers,
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
                    pairs.append({
                        "doc_id": str(doc.id),
                        "check_id": str(check_id),
                    })
                    total_checks += 1

                processed_docs += 1

            except Exception as e:
                errors += 1
                logger.exception(
                    "CheckPlanner: failed to plan checks for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
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
    
    