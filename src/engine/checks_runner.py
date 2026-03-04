"""
Stage 8 CheckRunner: playbook-based checks executor.

Назначение:
- Запускает playbook-checks по уже классифицированным документам сделки.
- Использует тот же playbook и CheckExecutor, что и Runner,
  но НЕ выполняет повторную классификацию документов и НЕ работает с триггерами.

Основные шаги:
1. Получает non-duplicate документы сделки через RunnerRepository.
2. Для каждого документа:
   - берёт doc_type и applicable_triggers (ожидается, что их заполнил Runner/классификатор),
   - выбирает релевантные checks из playbook,
   - формирует один full-text chunk,
   - выполняет CheckExecutor.execute и сохраняет результат в check_results
     через асинхронный UnitOfWork (db_uow).
3. Возвращает агрегированную статистику по run'у (processed_docs, total_checks,
   failed_checks, errors).

Использование:
- В async-коде:
    async with db_uow() as uow:
        runner = CheckRunner(llm_client)
        summary = await runner.run_deal_checks(deal_id, run_id)
"""

import uuid

from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from engine.checks.executor import CheckExecutor
from engine.playbook.loader import load_default_playbook

logger = get_logger(__name__)


class CheckRunner:
    """
    Stage 8 CheckRunner: запускает playbook-checks по уже классифицированным документам сделки.

    Использование:
      - Ожидается, что doc.doc_type и doc.applicable_triggers уже заполнены
        Stage 7/8 классификатором/Runner'ом.
      - Вызывает только слой checks (playbook + CheckExecutor), без повторной
        классификации и без работы с триггерами на уровне документов.

    Архитектура:
      - async, работает через db_uow() (тот же UoW, что и Runner).
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

        Шаги:
          1) Один раз загружаем playbook.
          2) В одном UoW получаем список non-duplicate документов сделки.
          3) Для каждого документа вызываем _run_checks_for_document(doc, run_id, playbook),
             оборачивая каждый документ в свой db_uow(), чтобы падение одного документа
             не откатывало весь run.
          4) Считаем processed_docs, total_checks, failed_checks, errors.

        Возвращает:
          dict с полями:
            - "deal_id": str
            - "run_id": str
            - "processed_docs": int
            - "total_checks": int
            - "failed_checks": int
            - "errors": int
        """
        logger.info(
            "CheckRunner started",
            deal_id=str(deal_id),
            run_id=str(run_id),
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

        logger.info(
            "CheckRunner: documents fetched",
            count=len(docs),
            deal_id=str(deal_id),
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
                    doc_id=str(doc.id),
                    deal_id=str(deal_id),
                    error=str(e),
                )
                # Не пробрасываем исключение, чтобы не падал весь run

        logger.info("CheckRunner completed", **summary)
        return summary

    async def _run_checks_for_document(
        self,
        doc,
        run_id: uuid.UUID,
        playbook,
    ) -> tuple[int, int]:
        """
        Выполнить все релевантные checks для одного документа в отдельном UoW.

        Возвращает:
          (total_checks_for_doc, failed_checks_for_doc)
        """
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results  # CheckResultRepository
            runner_repo = RunnerRepository(uow.session)  # если понадобится дополнительно

            doc_type = getattr(doc, "doc_type", "") or ""
            applicable_triggers: list[str] = getattr(doc, "applicable_triggers", None) or []

            # Выбираем checks с учётом doc_type и триггеров
            checks = playbook.get_conditional_checks(doc_type, applicable_triggers)

            # Готовим один full-text chunk
            text = getattr(doc, "text", "") or ""
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
                        getattr(conditional, "trigger", None) if conditional is not None else None
                    )

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
                }

                await repo.create(dto)
            # Коммит делает db_uow() при выходе из контекста

        return total_checks, failed_checks
