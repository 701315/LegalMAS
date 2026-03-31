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

                # ВАЖНО: после успешной обработки документа увеличиваем прогресс Run.
                # Это даёт живой прогресс: "N из M документов проверено".
                if self.run_repo is not None:
                    try:
                        await self.run_repo.increment_completed_checks(run_id)
                    except Exception as e:
                        # Ошибка прогресса не должна ломать сами проверки.
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

        Профиль документа:
        - В начале метода мы читаем:
            * doc_type  из doc.doc_type,
            * applicable_triggers из doc.applicable_triggers.
        - Эта пара (doc_type, applicable_triggers) считается «профилем документа».
        - На основе этого профиля выбираются проверки:
            * global_checks = playbook.get_conditional_checks(doc_type, applicable_triggers)
              — глобальные проверки из плейбука, которые зависят от триггеров;
            * doc_type_checks = DocTypeCheckLoader.load_checks_for_doc(...)
              — doc-type-специфичные проверки из YAML для данного doc_type,
                отфильтрованные по required_triggers/triggers.any.

        Иными словами:
        - Если профиль документа меняется (другой doc_type или другой набор
          applicable_triggers), то и набор checks для этого документа меняется.
        - Это позволяет включать/выключать сценарии (ипотека, маткапитал,
          наследование, сельхозземля и т.п.) через YAML-блоки trigger_definitions
          и compliance_rules, не трогая сам CheckRunner.

        Важно по реализации:
        - Здесь мы создаём DocumentContentService на сессии текущего UoW,
          чтобы читать layout/clause tree и собирать чанки.
        - Чанки передаются в CheckExecutor, который сам делает retrieval
          и вызывает детекторы (rules/LLM).

        Возвращает:
          (total_checks_for_doc, failed_checks_for_doc)
        """
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results  # ResultRepository

            # 1. Подготовка типов и триггеров
            doc_type = getattr(doc, "doc_type", "") or ""
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
                    "checks_mode": self.checks_mode,
                },
            )

            # 2. Выбор checks: глобальные из плейбука + doc-type из YAML (в зависимости от режима)
            global_checks = playbook.get_conditional_checks(doc_type, applicable_triggers)
            doc_type_checks = self.doc_type_loader.load_checks_for_doc(
                doc_type=doc_type,
                applicable_triggers=applicable_triggers,
            )

            mode = self.checks_mode
            if mode == "global_only":
                checks = global_checks
            elif mode == "doc_type_only":
                checks = doc_type_checks
            else:  # "global_and_doc_type" по умолчанию
                checks = global_checks + doc_type_checks

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

            # Диагностика пропущенных conditional-checks
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

            # 3. Получение чанков по документу
            content_service = DocumentContentService(
                session=uow.session,
            )

            # ВАЖНО:
            # - Раньше мы брали один чанк = одна листовая клауза (get_chunks).
            # - Теперь используем get_retrieval_chunks_for_checks, который:
            #     * берёт leaf-клаузу как основу,
            #     * режет длинные клаузы на под-чанки,
            #     * может отдавать разный набор уровней (subclause/section/clause).
            #
            # Здесь мы больше не захардкоживаем уровни, а берём их из retrieval-конфига
            # КАЖДОГО check'а. Но сами чанки считаем один раз на документ,
            # а не заново для каждого check, поэтому:
            #   1) сначала считаем "широкий" набор уровней для документа,
            #   2) а уже CheckExecutor использует required_kind/rerank/context_k.
            #
            # Для простоты и обратной совместимости:
            # - берём union уровней по всем checks документа,
            # - если ни у кого levels не заданы — используем ["subclause", "section"].
            all_levels: set[str] = set()
            for chk in checks:
                retr_cfg = getattr(chk, "retrieval", None)
                if retr_cfg and getattr(retr_cfg, "levels", None):
                    try:
                        all_levels.update(str(l).lower() for l in retr_cfg.levels)
                    except Exception:
                        # На всякий случай не ломаемся на странных данных
                        pass

            if not all_levels:
                # дефолт как было раньше
                levels_for_doc = ["subclause", "section"]
            else:
                # фиксируем порядок: subclause, clause, section
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
                        "run_id": str(run_id),
                        "chunk_count": len(chunks),
                        "max_chunks": MAX_CHUNKS_PER_DOC,
                    },
                )
                chunks = chunks[:MAX_CHUNKS_PER_DOC]

            # Ограничиваем длину текста в чанках
            safe_chunks: list[dict] = []
            for ch in chunks:
                text = ch.get("text") or ""
                if len(text) > MAX_CHUNK_TEXT_CHARS:
                    logger.warning(
                        "CheckRunner: chunk text truncated",
                        extra={
                            "doc_id": str(getattr(doc, "id", None)),
                            "run_id": str(run_id),
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

            # 4. Запуск checks по чанкам
            for check in checks:
                exec_result = self.executor.execute(doc, check, safe_chunks)
                total_checks += 1

                if exec_result.get("result") == "fail":
                    failed_checks += 1

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

                    quality_flags["raw"] = raw

                # raw structured_data от CheckExecutor
                structured_data_raw = exec_result.get("structured_data")

                # Нормализация structured_data под контракт StructuredField:
                # ожидаем формат {field_name: {value, unit?, source?, confidence?, found?, location?, qc?}}
                structured_data: dict[str, Any] | None = None
                if isinstance(structured_data_raw, dict):
                    structured_data = {}
                    for field_name, field_val in structured_data_raw.items():
                        # Если уже новый формат (dict с ключом "value") — не трогаем
                        if isinstance(field_val, dict) and "value" in field_val:
                            structured_data[field_name] = field_val
                            continue

                        # Старый формат: поле = простое значение (строка/число и т.п.)
                        structured_data[field_name] = {
                            "value": field_val,
                        }

                # Универсальная поддержка red_flags из structured_data
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

                conditional = getattr(check, "conditional", None)
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

                check_origin = getattr(check, "origin", None)

                page = exec_result.get("page")
                clause_uid = exec_result.get("clause_uid")
                element_id = exec_result.get("element_id")
                bbox = exec_result.get("bbox")

                await repo.create(
                    run_id=run_id,
                    document_id=doc.id,
                    check_id=exec_result["check_id"],
                    check_name=exec_result["check_name"],
                    result=exec_result["result"],
                    severity=exec_result["severity"],
                    value_text=value_text,
                    evidence_ref=evidence_ref,
                    confidence=exec_result.get("confidence"),
                    detector_used=detector_method,
                    quality_flags=quality_flags or None,
                    structured_data=structured_data,
                    conditional_check_triggered=is_conditional,
                    trigger_name=trigger_name,
                    origin=check_origin,
                    playbook_version_id=self.playbook_version_id,
                    page=page,
                    clause_uid=clause_uid,
                    element_id=element_id,
                    bbox=bbox,
                )

            # помечаем документ как полностью проверенный
            doc_repo = DocumentRepository(uow.session)
            await doc_repo.set_completed(doc.id)
            # Коммит делает db_uow() при выходе из контекста

        return total_checks, failed_checks
    