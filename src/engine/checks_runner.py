"""
Stage 8 CheckRunner: playbook-based checks executor.

Назначение:
- Запускает playbook-checks по уже классифицированным документам сделки.
- Использует playbook и CheckExecutor, но НЕ выполняет повторную классификацию
  документов и НЕ работает с триггерами на уровне запуска пайплайна.

Основные шаги:
1. Получает non-duplicate документы сделки через RunnerRepository.
2. Для каждого документа:
   - берёт doc_type и applicable_triggers (ожидается, что их заполнил классификатор),
   - выбирает релевантные checks из playbook,
   - формирует один full-text chunk,
   - выполняет CheckExecutor.execute и сохраняет результат в check_results.
3. Возвращает агрегированную статистику по run'у (processed_docs, total_checks,
   failed_checks, errors).

Использование:
    async with db_uow() as uow:
        runner = CheckRunner(llm_client)
        summary = await runner.run_deal_checks(deal_id, run_id)

Ограничения / прод-заметки:
- Есть мягкий лимит на количество документов для одного Run (MAX_DOCS_PER_RUN).
- Есть мягкий лимит на длину текста документа (MAX_TEXT_CHARS), чтобы не уронить LLM.
- Ошибки по отдельным документам не валят весь Run; считаются в summary["errors"].
"""


import time
import uuid
from typing import Tuple

from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from engine.checks.executor import CheckExecutor
from engine.playbook.loader import load_default_playbook

logger = get_logger(__name__)

# Мягкие лимиты для прод-окружения (можно вынести в settings)
MAX_DOCS_PER_RUN = 500
MAX_TEXT_CHARS = 100_000


class CheckRunner:
    """
    Stage 8 CheckRunner: запускает playbook-checks по уже классифицированным документам сделки.

    Ожидания:
    - doc.doc_type и doc.applicable_triggers уже заполнены классификатором.
    - doc.text содержит текст документа (или как минимум ключевые части для checks).

    Архитектура:
    - async, работает через db_uow().
    - На уровне сделки:
        1) вытаскивает non-duplicate документы по deal_id;
        2) по каждому документу запускает _run_checks_for_document в отдельном UoW;
        3) накапливает агрегированную статистику по run'у.
    - На уровне документа:
        1) выбирает релевантные checks из playbook по doc_type и applicable_triggers;
        2) формирует один full-text chunk;
        3) прогоняет checks через CheckExecutor;
        4) сохраняет результаты в check_results через UoW.
    """

    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client
        self.executor = CheckExecutor(llm_client)

    async def run_deal_checks(self, deal_id: uuid.UUID, run_id: uuid.UUID) -> dict:
        """
        Выполнить checks по всем non-duplicate документам сделки.

        Вход:
          - deal_id: UUID сделки.
          - run_id: UUID сущности Run (создаётся снаружи).

        Возвращает dict:
          - "deal_id": str
          - "run_id": str
          - "processed_docs": int
          - "total_checks": int
          - "failed_checks": int
          - "errors": int
        """
        start_time = time.time()

        logger.info(
            "CheckRunner started",
            extra={
                "deal_id": str(deal_id),
                "run_id": str(run_id),
            },
        )

        summary: dict = {
            "deal_id": str(deal_id),
            "run_id": str(run_id),
            "processed_docs": 0,
            "total_checks": 0,
            "failed_checks": 0,
            "errors": 0,
        }

        # Один playbook на весь run
        playbook = load_default_playbook()

        # Один UoW для получения списка документов
        async with db_uow() as uow_for_docs:
            runner_repo = RunnerRepository(uow_for_docs.session)
            docs = await runner_repo.get_non_duplicate_docs(deal_id)

        if not docs:
            logger.info(
                "CheckRunner: no non-duplicate documents to process",
                extra={
                    "deal_id": str(deal_id),
                    "run_id": str(run_id),
                },
            )
            logger.info(
                "CheckRunner completed",
                extra={
                    **summary,
                    "duration_sec": time.time() - start_time,
                },
            )
            return summary

        if len(docs) > MAX_DOCS_PER_RUN:
            logger.warning(
                "CheckRunner: document count exceeds max, truncating",
                extra={
                    "deal_id": str(deal_id),
                    "run_id": str(run_id),
                    "count": len(docs),
                    "max_docs": MAX_DOCS_PER_RUN,
                },
            )
            docs = docs[:MAX_DOCS_PER_RUN]

        logger.info(
            "CheckRunner: documents fetched",
            extra={
                "deal_id": str(deal_id),
                "run_id": str(run_id),
                "count": len(docs),
            },
        )

        # Отдельный UoW на каждый документ
        for doc in docs:
            try:
                checks_count, failed_count = await self._run_checks_for_document(
                    doc, run_id, playbook
                )
                summary["processed_docs"] += 1
                summary["total_checks"] += checks_count
                summary["failed_checks"] += failed_count
            except Exception as e:
                summary["errors"] += 1
                logger.error(
                    "CheckRunner: checks failed for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(deal_id),
                        "run_id": str(run_id),
                        "error": str(e),
                    },
                )
                # Не пробрасываем исключение, чтобы не падал весь run

        duration_sec = time.time() - start_time
        logger.info(
            "CheckRunner completed",
            extra={
                **summary,
                "duration_sec": duration_sec,
            },
        )
        return summary

    async def _run_checks_for_document(
        self,
        doc,
        run_id: uuid.UUID,
        playbook,
    ) -> Tuple[int, int]:
        """
        Выполнить все релевантные checks для одного документа в отдельном UoW.

        Возвращает:
          (total_checks_for_doc, failed_checks_for_doc)
        """
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results  # CheckResultRepository

            doc_type = getattr(doc, "doc_type", "") or ""
            # Нормализуем applicable_triggers в список строк
            raw_triggers = getattr(doc, "applicable_triggers", None) or []
            if isinstance(raw_triggers, list):
                applicable_triggers = [t for t in raw_triggers if isinstance(t, str)]
            else:
                applicable_triggers = []

            logger.debug(
                "CheckRunner: running checks for document",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "deal_id": str(getattr(doc, "deal_id", "")),
                    "run_id": str(run_id),
                    "doc_type": doc_type,
                    "triggers": applicable_triggers,
                },
            )

            # Выбираем checks с учётом doc_type и триггеров
            checks = playbook.get_conditional_checks(doc_type, applicable_triggers)

            if not checks:
                logger.info(
                    "CheckRunner: no checks for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
                        "run_id": str(run_id),
                        "doc_type": doc_type,
                        "triggers": applicable_triggers,
                    },
                )
                return 0, 0

            # Готовим один full-text chunk с мягким ограничением длины
            text = getattr(doc, "text", "") or ""
            orig_len = len(text)
            if orig_len > MAX_TEXT_CHARS:
                logger.warning(
                    "CheckRunner: document text truncated for checks",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
                        "run_id": str(run_id),
                        "orig_len": orig_len,
                        "max_len": MAX_TEXT_CHARS,
                    },
                )
                text = text[:MAX_TEXT_CHARS]

            chunks = [
                {
                    "id": f"{doc.id}-full",
                    "text": text,
                    "metadata": {"doc_id": str(doc.id)},
                }
            ]

            for check in checks:
                exec_result = self.executor.execute(doc, check, chunks)
                total_checks += 1

                if exec_result.get("result") == "fail":
                    failed_checks += 1

                # --- Маппинг exec_result -> DTO для CheckResult ---
                reason = exec_result.get("reason")
                evidence = exec_result.get("evidence") or ""
                detector_method = exec_result.get("detector_method")
                raw = exec_result.get("raw") or {}

                # value_text: краткое объяснение для человека
                value_text = reason or (evidence[:500] if evidence else None)

                # evidence_ref: пока просто сниппет; позже может стать S3 URI
                evidence_ref = evidence or None

                # quality_flags: вытащим ключевую диагностическую инфу из raw
                quality_flags: dict = {}

                if isinstance(raw, dict):
                    source = raw.get("source")
                    if source:
                        quality_flags["source"] = source

                    rules_conf = raw.get("rules_confidence")
                    if rules_conf is not None:
                        quality_flags["rules_confidence"] = rules_conf

                    llm_conf = raw.get("llm_confidence")
                    if llm_conf is not None:
                        quality_flags["llm_confidence"] = llm_conf

                    # по желанию сохраняем весь raw для дебага
                    quality_flags["raw"] = raw

                # structured_data пока не используем (зарезервировано под ExtractionConfig)
                structured_data = exec_result.get("structured_data")

                # conditional: поддерживаем и старый dict, и новую модель ConditionalConfig
                conditional = getattr(check, "conditional", None)
                if isinstance(conditional, dict):
                    is_conditional = bool(conditional)
                    trigger_name = conditional.get("trigger")
                else:
                    # Pydantic-модель ConditionalConfig или None
                    is_conditional = bool(conditional)
                    trigger_name = (
                        getattr(conditional, "trigger", None)
                        if conditional is not None
                        else None
                    )

                # Источник проверки: пока считаем, что CheckRunner использует глобальный плейбук
                origin = "global_playbook"

                dto = {
                    "run_id": run_id,
                    "document_id": doc.id,
                    "check_id": exec_result["check_id"],
                    "check_name": exec_result["check_name"],
                    "result": exec_result["result"],  # "fail" / "pass" / "unclear"
                    "severity": exec_result["severity"],
                    "value_text": value_text,
                    "evidence_ref": evidence_ref,
                    "confidence": exec_result.get("confidence"),
                    "detector_used": detector_method,
                    "quality_flags": quality_flags or None,
                    "structured_data": structured_data,
                    "conditional_check_triggered": is_conditional,
                    "trigger_name": trigger_name,
                    # НОВЫЕ ПОЛЯ: координаты evidence / источник плейбука
                    "origin": origin,
                    "page": exec_result.get("page"),
                    "clause_uid": exec_result.get("clause_uid"),
                    "element_id": exec_result.get("element_id"),
                    "bbox": exec_result.get("bbox"),
                }

                await repo.create(dto)

            # Коммит делает db_uow() при выходе из контекста

        return total_checks, failed_checks
