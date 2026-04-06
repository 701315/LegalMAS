# src/engine/checks_runner.py

"""
CheckRunner: playbook-based checks executor.

Назначение:
- Запускает playbook-checks по уже классифицированным документам сделки.
- Использует playbook и CheckExecutor, но НЕ выполняет повторную классификацию
  документов и НЕ работает с триггерами на уровне запуска пайплайна.

Профиль документа:
- Под «профилем документа» понимается пара:
    (doc_type, applicable_triggers).
- doc_type заполняется каскадом классификации (HybridClassifier).
- applicable_triggers формируются на основе:
    * типовых триггеров из YAML (trigger_definitions) для данного doc_type,
    * фактических срабатываний TriggerDetector (семья, текст).
- Именно этот профиль (doc_type + applicable_triggers) определяет,
  какие проверки будут выбраны для документа и как будет формироваться DD Grid.

Новая архитектура (после рефакторинга):

1. Получаем non-duplicate документы сделки через RunnerRepository.
2. Для каждого документа:
   - берём doc_type и applicable_triggers (классификатор уже заполнил),
   - выбираем релевантные checks из playbook и YAML типа документа
     (в зависимости от режима),
   - через DocumentContentService получаем ЧАНКИ по листовым клаузам
     (структурно осмысленные куски текста, а не один "простыню" целиком),
   - выполняем CheckExecutor.execute(doc, check, chunks),
   - сохраняем результат в check_results.
3. Возвращаем агрегированную статистику по run'у
   (processed_docs, total_checks, failed_checks, errors).
"""

import time
import uuid
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from engine.checks.executor import CheckExecutor
from engine.content.document_content_service import DocumentContentService
from engine.doc_type_checks.loader import DocTypeCheckLoader

logger = get_logger(__name__)

# Мягкие лимиты для прод-окружения (можно вынести в settings)
MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50        # мягкий предохранитель от "развалившихся" прогонов
MAX_CHUNKS_PER_DOC = 2000      # защита от "взрывных" деревьев
MAX_CHUNK_TEXT_CHARS = 20_000  # защита от слишком длинных клауз в одном чанке


class CheckRunner:
    """
    Stage 8 CheckRunner: запускает playbook-checks по уже классифицированным документам сделки.

    Ожидания:
    - doc.doc_type и doc.applicable_triggers уже заполнены классификатором.
    - DocumentContentService умеет отдавать чанки по документу:
      один чанк = одна листовая клауза (пункт договора) с полным текстом.

    Архитектура:
    - async, работает через db_uow().
    - На уровне сделки:
        1) вытаскивает non-duplicate документы по deal_id;
        2) по каждому документу запускает _run_checks_for_document в отдельном UoW;
        3) накапливает агрегированную статистику по run'у.
    - На уровне документа:
        1) выбирает релевантные checks из playbook по doc_type и триггерам,
           ДОПОЛНИТЕЛЬНО подмешивает doc-type-специфичные проверки из YAML
           (если это разрешено режимом);
        2) получает чанки через DocumentContentService;
        3) прогоняет checks через CheckExecutor;
        4) сохраняет результаты в check_results через репозиторий.
    """

    def __init__(
        self,
        llm_client,
        playbook_version_id: uuid.UUID | None = None,
        checks_mode: str = "global_and_doc_type",
        run_repo: Optional[RunRepository] = None,
    ) -> None:
        """
        llm_client — клиент для LLM.

        playbook_version_id:
            Идентификатор версии плейбука, под которой выполняются проверки.
            Сохраняется в CheckResult.playbook_version_id для аудита.

        checks_mode:
            Режим набора проверок для этого запуска:
            - "global_only"
            - "doc_type_only"
            - "global_and_doc_type" (по умолчанию).

        run_repo:
            Репозиторий для сущности Run.
            Нужен, чтобы после каждого успешно обработанного документа
            увеличивать счётчик completed_checks и показывать живой прогресс.
            Если не передан, прогресс Run трогать не будем.
        """
        self.llm_client = llm_client
        self.executor = CheckExecutor(llm_client)
        self.playbook_version_id = playbook_version_id
        self.doc_type_loader = DocTypeCheckLoader()
        self.checks_mode = checks_mode
        self.run_repo = run_repo

    async def run_deal_checks(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
        playbook,
        checks_mode: str | None = None,
    ) -> dict:
        """
        Выполнить checks по всем non-duplicate документам сделки.

        Вход:
          - deal_id: UUID сделки.
          - run_id: UUID сущности Run (создаётся снаружи).
          - playbook: PlaybookDefinition (загружен из compiled_checks).

        Возвращает dict:
          - "deal_id": str
          - "run_id": str
          - "processed_docs": int
          - "total_checks": int
          - "failed_checks": int
          - "errors": int
        """
        start_time = time.time()

        if checks_mode:
            self.checks_mode = checks_mode

        logger.info(
            "CheckRunner started",
            extra={
                "deal_id": str(deal_id),
                "run_id": str(run_id),
                "checks_mode": self.checks_mode,
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

                if self.run_repo is not None:
                    try:
                        await self.run_repo.increment_completed_checks(run_id)
                    except Exception as e:
                        logger.warning(
                            "CheckRunner: failed to increment completed_checks",
                            extra={
                                "run_id": str(run_id),
                                "doc_id": str(getattr(doc, "id", None)),
                                "error": str(e),
                            },
                        )

            except Exception as e:
                summary["errors"] += 1

                if summary["errors"] > MAX_ERRORS_PER_RUN:
                    logger.error(
                        "CheckRunner: too many errors, aborting remaining checks",
                        extra={
                            "deal_id": str(deal_id),
                            "run_id": str(run_id),
                            "errors": summary["errors"],
                            "max_errors": MAX_ERRORS_PER_RUN,
                        },
                    )
                    break

                logger.error(
                    "CheckRunner: checks failed for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(deal_id),
                        "run_id": str(run_id),
                        "error": str(e),
                    },
                )

        duration_sec = time.time() - start_time
        logger.info(
            "CheckRunner completed",
            extra={
                **summary,
                "duration_sec": duration_sec,
            },
        )
        return summary

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
                "CheckRunner: too many documents for run planning, truncating",
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
                    checks,
                    mode,
                    doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._select_checks_for_document(doc, playbook)

                logger.info(
                    "CheckRunner: planned checks for document",
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

                    pairs.append(
                        {
                            "doc_id": str(doc.id),
                            "check_id": str(check_id),
                        }
                    )
                    total_checks += 1

                processed_docs += 1

            except Exception as e:
                errors += 1
                logger.exception(
                    "CheckRunner: failed to plan checks for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
                        "run_id": str(run_id),
                        "error": str(e),
                    },
                )

                if errors >= MAX_ERRORS_PER_RUN:
                    logger.error(
                        "CheckRunner: too many errors during planning, stopping",
                        extra={
                            "deal_id": str(deal_id),
                            "run_id": str(run_id),
                            "errors": errors,
                            "max_errors": MAX_ERRORS_PER_RUN,
                        },
                    )
                    break

        return {
            "pairs": pairs,
            "processed_docs": processed_docs,
            "total_checks": total_checks,
            "errors": errors,
        }

    def _get_document_profile(self, doc) -> tuple[str, list[str]]:
        """
        Вернуть профиль документа:
        - doc_type
        - applicable_triggers
        """
        doc_type = getattr(doc, "doc_type", "") or ""
        raw_triggers = getattr(doc, "applicable_triggers", None) or []

        if isinstance(raw_triggers, list):
            applicable_triggers = [t for t in raw_triggers if isinstance(t, str)]
        else:
            applicable_triggers = []

        return doc_type, applicable_triggers

    def _select_checks_for_document(
        self,
        doc,
        playbook,
    ) -> tuple[list[Any], str, str, list[str], list[Any], list[Any]]:
        """
        Подобрать checks для документа по текущему checks_mode.

        Возвращает:
        - checks
        - mode
        - doc_type
        - applicable_triggers
        - global_checks
        - doc_type_checks
        """
        doc_type, applicable_triggers = self._get_document_profile(doc)

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
        ) = self._select_checks_for_document(doc, playbook)

        target_check_id = str(check_id)

        for check in checks:
            current_check_id = str(getattr(check, "id", ""))
            if current_check_id == target_check_id:
                return check

        logger.warning(
            "CheckRunner: target check not applicable for document",
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

    async def _build_safe_chunks_for_checks(
        self,
        session: AsyncSession,
        doc,
        checks: list[Any],
    ) -> list[dict]:
        """
        Собрать safe_chunks для одного документа и набора checks.

        Это общий helper для:
        - старого _run_checks_for_document(...)
        - новой Celery-task run_single_check(...)
        """
        content_service = DocumentContentService(session=session)

        all_levels: set[str] = set()
        for chk in checks:
            retr_cfg = getattr(chk, "retrieval", None)
            if retr_cfg and getattr(retr_cfg, "levels", None):
                try:
                    all_levels.update(str(l).lower() for l in retr_cfg.levels)
                except Exception:
                    pass

        if not all_levels:
            levels_for_doc = ["subclause", "section"]
        else:
            preferred_order = ["subclause", "clause", "section"]
            levels_for_doc = [
                lvl for lvl in preferred_order if lvl in all_levels
            ] or list(all_levels)

        chunks = await content_service.get_retrieval_chunks_for_checks(
            doc_id=doc.id,
            levels=levels_for_doc,
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
        )

        if len(chunks) > MAX_CHUNKS_PER_DOC:
            logger.warning(
                "CheckRunner: too many chunks for document, truncating",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "chunk_count": len(chunks),
                    "max_chunks": MAX_CHUNKS_PER_DOC,
                },
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        safe_chunks: list[dict] = []
        for ch in chunks:
            text = ch.get("text") or ""
            if len(text) > MAX_CHUNK_TEXT_CHARS:
                logger.warning(
                    "CheckRunner: chunk text truncated",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "chunk_id": ch.get("id"),
                        "orig_len": len(text),
                        "max_len": MAX_CHUNK_TEXT_CHARS,
                    },
                )
                text = text[:MAX_CHUNK_TEXT_CHARS]

            safe_chunks.append(
                {
                    "id": ch.get("id"),
                    "text": text,
                    "metadata": ch.get("metadata") or {},
                }
            )

        if not safe_chunks:
            safe_chunks = [
                {
                    "id": f"{doc.id}:empty",
                    "text": "",
                    "metadata": {"doc_id": str(doc.id)},
                }
            ]

        return safe_chunks

    def _normalize_check_result(
        self,
        exec_result: dict,
        check,
    ) -> dict[str, Any]:
        """
        Нормализовать DTO от CheckExecutor под поля CheckResult.
        """
        reason = exec_result.get("reason")
        evidence = exec_result.get("evidence") or ""
        detector_method = exec_result.get("detector_method")
        raw = exec_result.get("raw") or {}

        value_text = reason or (evidence[:500] if evidence else None)
        evidence_ref = evidence or None

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

            # Новые флаги по LLM (технические, но полезно видеть их в CheckResult):
            llm_error_type = raw.get("llm_error_type")
            if llm_error_type:
                quality_flags["llm_error_type"] = llm_error_type

            llm_required = raw.get("llm_required")
            if llm_required is not None:
                quality_flags["llm_required"] = bool(llm_required)

            llm_degraded = raw.get("llm_degraded")
            if llm_degraded is not None:
                quality_flags["llm_degraded"] = bool(llm_degraded)

            rules_llm_decision = raw.get("rules_llm_decision")
            if rules_llm_decision:
                quality_flags["rules_llm_decision"] = rules_llm_decision

            quality_flags["raw"] = raw

        structured_data_raw = exec_result.get("structured_data")

        structured_data: dict[str, Any] | None = None
        if isinstance(structured_data_raw, dict):
            structured_data = {}
            for field_name, field_val in structured_data_raw.items():
                if isinstance(field_val, dict) and "value" in field_val:
                    structured_data[field_name] = field_val
                    continue

                structured_data[field_name] = {
                    "value": field_val,
                }

        if structured_data:
            rf_payload = structured_data.get("red_flags")
            red_from_struct: Any | None = None

            if rf_payload is not None:
                if isinstance(rf_payload, dict):
                    red_from_struct = rf_payload.get("value")
                else:
                    red_from_struct = rf_payload

            codes: list[str] = []
            if red_from_struct:
                if isinstance(red_from_struct, str):
                    codes = [
                        c.strip()
                        for c in red_from_struct.split(",")
                        if c and c.strip()
                    ]
                elif isinstance(red_from_struct, list):
                    codes = [
                        str(c).strip()
                        for c in red_from_struct
                        if str(c).strip()
                    ]
                else:
                    codes = [str(red_from_struct).strip()]

            if codes:
                existing = quality_flags.get("red_flags")
                if isinstance(existing, list):
                    existing.extend(codes)
                elif isinstance(existing, str):
                    merged = [
                        e.strip()
                        for e in existing.split(",")
                        if e and e.strip()
                    ] + codes
                    quality_flags["red_flags"] = merged
                elif existing is None:
                    quality_flags["red_flags"] = codes

        conditional = getattr(check, "conditional", None) if check is not None else None
        if isinstance(conditional, dict):
            is_conditional = bool(conditional)
            trigger_name = conditional.get("trigger")
        else:
            is_conditional = bool(conditional)
            trigger_name = (
                getattr(conditional, "trigger", None)
                if conditional is not None
                else None
            )

        check_origin = getattr(check, "origin", None) if check is not None else None

        return {
            "value_text": value_text,
            "evidence_ref": evidence_ref,
            "detector_used": detector_method,
            "quality_flags": quality_flags or None,
            "structured_data": structured_data,
            "conditional_check_triggered": is_conditional,
            "trigger_name": trigger_name,
            "origin": check_origin,
            "page": exec_result.get("page"),
            "clause_uid": exec_result.get("clause_uid"),
            "element_id": exec_result.get("element_id"),
            "bbox": exec_result.get("bbox"),
        }

    async def _save_check_result(
        self,
        repo,
        run_id: uuid.UUID,
        doc,
        check,
        exec_result: dict,
    ):
        """
        Сохранить результат одной проверки в check_results идемпотентно
        по ключу (run_id, document_id, check_id).

        В новой архитектуре одна пара (run, doc, check) должна иметь
        одну материализованную запись, которая обновляется при retry /
        rerun / timeout recovery.

        ВАЖНО:
        - здесь мы решаем, какой execution_status поставить:
            * "SUCCESS"  — бизнес-результат корректен, даже если LLM деградировал,
                            но rules были достаточно сильны;
            * "TIMEOUT" / "FAILED_LLM" — если без LLM честный ответ невозможен,
                            а LLM дал ошибку (Variant B);
            * "FAILED"   — технические ошибки на уровне организации проверки.
        """
        normalized = self._normalize_check_result(exec_result, check)

        # Технические флаги от CheckExecutor:
        llm_error_type = exec_result.get("llm_error_type")
        llm_required = bool(exec_result.get("llm_required") or False)
        llm_degraded = bool(exec_result.get("llm_degraded") or False)
        rules_llm_decision = exec_result.get("rules_llm_decision")

        # По умолчанию считаем, что check исполнен успешно.
        execution_status = "SUCCESS"
        error_details: dict[str, Any] | None = None

        # Если LLM был обязателен и есть ошибка — это не "честный" SUCCESS.
        # Здесь мы не различаем конкретный тип LLM-ошибки детально, это можно
        # сделать позже, если появится необходимость.
        if llm_required and llm_error_type:
            # Базово считаем это TIMEOUT/FAILED_LLM, в зависимости от типа ошибки.
            if "timeout" in str(llm_error_type).lower():
                execution_status = "TIMEOUT"
            else:
                execution_status = "FAILED_LLM"

            error_details = {
                "type": "llm_error",
                "llm_error_type": llm_error_type,
                "llm_required": llm_required,
                "llm_degraded": llm_degraded,
                "rules_llm_decision": rules_llm_decision,
            }

        # Если LLM не был критичен (rules дали достаточно сильный ответ),
        # но была деградация, мы оставляем SUCCESS, но сохраняем тех. детали в quality_flags.
        # Для этого нам достаточно того, что _normalize_check_result уже положил
        # llm_* флаги внутрь quality_flags["raw"].

        return await repo.upsert_single_check_result(
            run_id=run_id,
            document_id=doc.id,
            check_id=exec_result["check_id"],
            check_name=exec_result["check_name"],
            result=exec_result["result"],
            severity=exec_result["severity"],
            value_text=normalized["value_text"],
            evidence_ref=normalized["evidence_ref"],
            confidence=exec_result.get("confidence"),
            detector_used=normalized["detector_used"],
            quality_flags=normalized["quality_flags"],
            structured_data=normalized["structured_data"],
            conditional_check_triggered=normalized["conditional_check_triggered"],
            trigger_name=normalized["trigger_name"],
            origin=normalized["origin"],
            playbook_version_id=self.playbook_version_id,
            page=normalized["page"],
            clause_uid=normalized["clause_uid"],
            element_id=normalized["element_id"],
            bbox=normalized["bbox"],
            execution_status=execution_status,
            error_details=error_details,
        )

    async def execute_single_check(
        self,
        *,
        session: AsyncSession,
        repo,
        doc,
        run_id: uuid.UUID,
        playbook,
        check_id: str,
        safe_chunks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Выполнить одну проверку (check_id) для одного документа и сохранить результат.

        ВАЖНО:
        - find_check_for_document(...) гарантирует, что мы не запустим check,
          который не применим к этому документу (doc_type/triggers).
        - safe_chunks можно передать снаружи (reuse между checks), либо
          они будут собраны заново для одного check.
        """
        check = self.find_check_for_document(doc, playbook, check_id)
        if check is None:
            logger.warning(
                "CheckRunner.execute_single_check: check not found or not applicable",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "deal_id": str(getattr(doc, "deal_id", "")),
                    "run_id": str(run_id),
                    "check_id": check_id,
                },
            )
            exec_result: dict[str, Any] = {
                "doc_id": str(getattr(doc, "id", None)),
                "check_id": check_id,
                "check_name": None,
                "result": "unclear",
                "severity": "unclear",
                "confidence": None,
                "detector_method": None,
                "reason": "check_not_applicable",
                "sources": [],
                "location": None,
                "raw": {
                    "source": "check_runner",
                    "error": "check_not_applicable_for_document",
                },
                "structured_data": None,
                "page": None,
                "clause_uid": None,
                "element_id": None,
                "bbox": None,
            }

            normalized = self._normalize_check_result(exec_result, check=None)

            await repo.upsert_single_check_result(
                run_id=run_id,
                document_id=doc.id,
                check_id=check_id,
                check_name=exec_result["check_name"],
                result=exec_result["result"],
                severity=exec_result["severity"],
                value_text=normalized["value_text"],
                evidence_ref=normalized["evidence_ref"],
                confidence=exec_result.get("confidence"),
                detector_used=normalized["detector_used"],
                quality_flags=normalized["quality_flags"],
                structured_data=normalized["structured_data"],
                conditional_check_triggered=normalized["conditional_check_triggered"],
                trigger_name=normalized["trigger_name"],
                origin=normalized["origin"],
                playbook_version_id=self.playbook_version_id,
                page=normalized["page"],
                clause_uid=normalized["clause_uid"],
                element_id=normalized["element_id"],
                bbox=normalized["bbox"],
                execution_status="FAILED",
                error_details={
                    "type": "check_not_applicable",
                    "message": "check not found or not applicable for this document",
                },
            )

            return {
                "exec_result": exec_result,
                "failed": False,
            }

        if safe_chunks is None:
            safe_chunks = await self._build_safe_chunks_for_checks(
                session=session,
                doc=doc,
                checks=[check],
            )

        exec_result = self.executor.execute(doc, check, safe_chunks)

        await self._save_check_result(
            repo=repo,
            run_id=run_id,
            doc=doc,
            check=check,
            exec_result=exec_result,
        )

        return {
            "exec_result": exec_result,
            "failed": exec_result.get("result") == "fail",
        }

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
            repo = uow.check_results

            (
                checks,
                mode,
                doc_type,
                applicable_triggers,
                global_checks,
                doc_type_checks,
            ) = self._select_checks_for_document(doc, playbook)

            logger.debug(
                "CheckRunner: running checks for document",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "deal_id": str(getattr(doc, "deal_id", "")),
                    "run_id": str(run_id),
                    "doc_type": doc_type,
                    "triggers": applicable_triggers,
                    "checks_mode": self.checks_mode,
                },
            )

            logger.info(
                "CheckRunner: checks selected for document",
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

            if not checks:
                logger.info(
                    "CheckRunner: no checks for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "deal_id": str(getattr(doc, "deal_id", "")),
                        "run_id": str(run_id),
                        "doc_type": doc_type,
                        "triggers": applicable_triggers,
                        "checks_mode": mode,
                    },
                )
                return 0, 0

            try:
                for check in getattr(playbook, "checks", []):
                    if getattr(check, "doc_types", None) and doc_type not in check.doc_types:
                        continue

                    conditional = getattr(check, "conditional", None)
                    if not conditional:
                        continue

                    if isinstance(conditional, dict):
                        trigger = conditional.get("trigger")
                    else:
                        trigger = getattr(conditional, "trigger", None)

                    if trigger and trigger not in applicable_triggers:
                        logger.info(
                            "CheckRunner: conditional check skipped (trigger not detected)",
                            extra={
                                "doc_id": str(getattr(doc, "id", None)),
                                "deal_id": str(getattr(doc, "deal_id", "")),
                                "run_id": str(run_id),
                                "doc_type": doc_type,
                                "check_id": getattr(check, "id", None),
                                "check_name": getattr(check, "name", None),
                                "required_trigger": trigger,
                                "doc_applicable_triggers": applicable_triggers,
                            },
                        )
            except Exception as e:
                logger.warning(
                    "CheckRunner: failed to log skipped conditional checks",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "run_id": str(run_id),
                        "error": str(e),
                    },
                )

            safe_chunks = await self._build_safe_chunks_for_checks(
                session=uow.session,
                doc=doc,
                checks=checks,
            )

            for check in checks:
                outcome = await self._execute_single_check_internal(
                    session=uow.session,
                    repo=repo,
                    doc=doc,
                    run_id=run_id,
                    check=check,
                    safe_chunks=safe_chunks,
                )
                total_checks += 1
                if outcome["failed"]:
                    failed_checks += 1

            doc_repo = DocumentRepository(uow.session)
            await doc_repo.set_completed(doc.id)

        return total_checks, failed_checks

    async def _execute_single_check_internal(
        self,
        *,
        session: AsyncSession,
        repo,
        doc,
        run_id: uuid.UUID,
        check,
        safe_chunks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Внутренний helper для старого batched-режима (_run_checks_for_document),
        чтобы не дублировать бизнес-логику.
        """
        if safe_chunks is None:
            safe_chunks = await self._build_safe_chunks_for_checks(
                session=session,
                doc=doc,
                checks=[check],
            )

        exec_result = self.executor.execute(doc, check, safe_chunks)
        await self._save_check_result(
            repo=repo,
            run_id=run_id,
            doc=doc,
            check=check,
            exec_result=exec_result,
        )

        return {
            "exec_result": exec_result,
            "failed": exec_result.get("result") == "fail",
        }
    
    