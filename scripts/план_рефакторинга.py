#!/usr/bin/env python3
"""
Планировщик рефакторинга для LegalMAS.
Анализирует God-классы и генерирует конкретный план разбиения.
"""

import os
from datetime import datetime

OUTPUT_DIR = "/home/vladi/projects/LegalMAS/scripts"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "план рефакторинга.md")


def generate_plan():
    plan = []
    p = plan.append

    p("# 🏗️ План рефакторинга LegalMAS")
    p(f"")
    p(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    p(f"**Масштаб:** 37 файлов > 500 строк, ~60K строк общий объём")
    p("")
    p("---")
    p("")

    # ================================================================
    # ПРИОРИТЕТ 1
    # ================================================================
    p("## 🔴 Приоритет 1: God-классы (делать первыми)")
    p("")

    # --- document_pipeline_view_service.py ---
    p("### 1.1 `src/services/document_pipeline_view_service.py` (2242 → ~6×350)")
    p("")
    p("**Проблема:** Один класс `DocumentPipelineViewService` с 28 методами.")
    p("Строит 6 стадий пайплайна, парсит clause-деревья, маппит чанки,")
    p("нормализует UID — всё в одном файле.")
    p("")
    p("**Стратегия:** Выделить каждую стадию в отдельный Stage Builder.")
    p("Основной сервис становится фасадом-оркестратором.")
    p("")
    p("```")
    p("src/services/pipeline_view/")
    p("├── __init__.py                    # реэкспорт DocumentPipelineViewService")
    p("├── service.py                     # ~120 строк — фасад-оркестратор")
    p("│                                  #   __init__, build, _base_meta,")
    p("│                                  #   _status_from_presence")
    p("│")
    p("├── representation.py              # ~100 строк — логика представлений")
    p("│                                  #   _stage_representation (строка 198)")
    p("│                                  #   _with_representation (строка 266)")
    p("│")
    p("├── stage_source.py                # ~70 строк")
    p("│                                  #   _build_source_stage (строка 295)")
    p("│")
    p("├── stage_primary.py               # ~70 строк")
    p("│                                  #   _build_primary_stage (строка 361)")
    p("│")
    p("├── stage_extract.py               # ~55 строк")
    p("│                                  #   _build_extract_stage (строка 428)")
    p("│")
    p("├── stage_pii.py                   # ~55 строк")
    p("│                                  #   _build_pii_stage (строка 480)")
    p("│                                  #   _build_layout_stage_from_payload (535)")
    p("│")
    p("├── stage_structure.py             # ~350 строк")
    p("│                                  #   _build_structure_stage (строка 1039)")
    p("│                                  #   _make_segment_dto (строка 1081)")
    p("│                                  #   _flatten_clause_tree (строка 1333)")
    p("│                                  #   _iter_structure_root_nodes (строка 1453)")
    p("│                                  #   _enrich_structure_with_text (строка 1487)")
    p("│                                  #   _inherit_structure_from_children (951)")
    p("│                                  #   _attach_structure_source_mapping (629)")
    p("│")
    p("├── stage_chunks.py                # ~400 строк")
    p("│                                  #   _build_chunks_stage (строка 1767)")
    p("│                                  #   _load_chunks_fallback (строка 2117)")
    p("│                                  #   _extract_chunks_from_snapshot (2173)")
    p("│")
    p("└── normalizers.py                 # ~80 строк — вспомогательные функции")
    p("                                   #   _normalize_uid (строки 712, 1355, 1571)")
    p("                                   #   _normalize_title (строка 1361)")
    p("                                   #   _normalize_int (строка 1367)")
    p("                                   #   _extract_clause_tree_text (строка 598)")
    p("                                   #   _chunk_sort_key (строки 748, 1609)")
    p("```")
    p("")
    p("**Как рефакторить:**")
    p("")
    p("```python")
    p("# src/services/pipeline_view/service.py — ПОСЛЕ рефакторинга")
    p("")
    p("class DocumentPipelineViewService:")
    p('    """Фасад: собирает стадии пайплайна из отдельных билдеров."""')
    p("")
    p("    def __init__(self, session: AsyncSession):")
    p("        self._session = session")
    p("        self._artifact_store = ArtifactStore()")
    p("        self._doc_repo = DocumentRepository(session)")
    p("        self._version_repo = DocumentVersionRepository(session)")
    p("        # билдеры стадий")
    p("        self._source = SourceStageBuilder(self._artifact_store)")
    p("        self._primary = PrimaryStageBuilder(self._artifact_store)")
    p("        self._extract = ExtractStageBuilder(self._artifact_store)")
    p("        self._pii = PiiStageBuilder(self._artifact_store)")
    p("        self._structure = StructureStageBuilder(session, self._artifact_store)")
    p("        self._chunks = ChunksStageBuilder(session, self._artifact_store)")
    p("")
    p("    async def build(self, document_id: UUID) -> DocumentPipelineViewResponseDTO:")
    p("        doc = await self._doc_repo.get(document_id)")
    p("        version = await self._version_repo.get_latest(document_id)")
    p("        meta = base_meta(doc)")
    p("        return DocumentPipelineViewResponseDTO(")
    p("            stages=[")
    p("                self._source.build(doc, version, meta),")
    p("                self._primary.build(doc, version, meta),")
    p("                self._extract.build(doc, version, meta),")
    p("                self._pii.build(doc, version, meta),")
    p("                await self._structure.build(doc, version, meta),")
    p("                await self._chunks.build(doc, version, meta),")
    p("            ]")
    p("        )")
    p("```")
    p("")
    p("**Трудоёмкость:** ~3-4 часа")
    p("**Риск:** Низкий — это read-only сервис, ничего не мутирует")
    p("")
    p("---")
    p("")

    # --- checks_runner.py ---
    p("### 1.2 `src/engine/checks_runner.py` (1211 → ~4×300)")
    p("")
    p("**Проблема:** Один класс `CheckRunner` — планирует, скоупит,")
    p("выполняет, нормализует и сохраняет проверки.")
    p("")
    p("**Стратегия:** Разделить на 4 модуля по ответственности.")
    p("")
    p("```")
    p("src/engine/checks/")
    p("├── __init__.py")
    p("├── runner.py                      # ~200 строк — оркестратор")
    p("│                                  #   __init__ (строка 85)")
    p("│                                  #   run_deal_checks (строка 125)")
    p("│                                  #   _run_checks_for_document (строка 1047)")
    p("│")
    p("├── planner.py                     # ~200 строк — планирование и скоупинг")
    p("│                                  #   plan_checks_for_run (строка 272)")
    p("│                                  #   _get_document_profile (строка 383)")
    p("│                                  #   _resolve_scope_flags (строка 399)")
    p("│                                  #   _filter_chunks_by_scope (строка 442)")
    p("│                                  #   _select_checks_for_document (строка 483)")
    p("│                                  #   find_check_for_document (строка 533)")
    p("│")
    p("├── executor.py                    # СУЩЕСТВУЕТ, расширить")
    p("│                                  #   execute_single_check (строка 932)")
    p("│                                  #   _execute_single_check_internal (1177)")
    p("│                                  #   _build_safe_chunks_for_checks (575)")
    p("│")
    p("└── result_normalizer.py           # ~200 строк")
    p("                                   #   _normalize_check_result (строка 668)")
    p("                                   #   _save_check_result (строка 842)")
    p("```")
    p("")
    p("**Ключевое решение:** У вас уже есть `src/engine/checks/executor.py` (674 строки).")
    p("Нужно решить: объединить с методами из `checks_runner.py` или держать раздельно.")
    p("Рекомендую: `executor.py` — низкоуровневое выполнение (детекторы, LLM),")
    p("`runner.py` — высокоуровневая оркестрация.")
    p("")
    p("**Трудоёмкость:** ~2-3 часа")
    p("**Риск:** Средний — затрагивает core бизнес-логику, нужны тесты")
    p("")
    p("---")
    p("")

    # ================================================================
    # ПРИОРИТЕТ 2
    # ================================================================
    p("## 🟡 Приоритет 2: Крупные файлы 800-1200 строк")
    p("")

    priority2_files = [
        (
            "src/classifiers/stage8/hybrid_classifier.py",
            1189,
            "Классификатор с 3 уровнями (filename → header → semantic)",
            "classifiers/stage8/",
            [
                "classifier.py — оркестратор (~200)",
                "feature_extractor.py — извлечение признаков (~300)",
                "scoring.py — скоринг и ранжирование (~300)",
                "fallback.py — фолбэк-логика (~200)",
            ],
        ),
        (
            "src/engine/content/chunk_snapshot_builder.py",
            1078,
            "Билдер снэпшотов чанков",
            "engine/content/",
            [
                "chunk_snapshot_builder.py — основная логика (~400)",
                "chunk_materializer.py — материализация чанков (~350)",
                "chunk_metadata.py — метаданные и маппинг (~250)",
            ],
        ),
        (
            "src/services/layout_language_filter.py",
            992,
            "Фильтр языков в лейауте",
            "services/",
            [
                "layout_language_filter.py — основной фильтр (~400)",
                "language_heuristics.py — эвристики определения (~300)",
                "layout_block_analyzer.py — анализ блоков (~250)",
            ],
        ),
        (
            "src/engine/content/document_content_service.py",
            968,
            "Сервис контента документа",
            "engine/content/",
            [
                "document_content_service.py — фасад (~300)",
                "content_loader.py — загрузка и кэширование (~350)",
                "content_transformer.py — трансформации (~250)",
            ],
        ),
        (
            "src/services/structure/pipeline.py",
            934,
            "Пайплайн структуры документа",
            "services/structure/",
            [
                "pipeline.py — оркестратор (~300)",
                "pipeline_stages.py — отдельные стадии (~350)",
                "pipeline_config.py — конфигурация (~200)",
            ],
        ),
        (
            "src/services/pdf_extractor.py",
            875,
            "Извлечение из PDF",
            "services/",
            [
                "pdf_extractor.py — основной экстрактор (~350)",
                "pdf_table_extractor.py — таблицы (~250)",
                "pdf_layout_parser.py — парсинг лейаута (~250)",
            ],
        ),
    ]

    for filepath, lines, desc, target_dir, modules in priority2_files:
        p(f"### `{filepath}` ({lines} строк)")
        p(f"")
        p(f"**Что делает:** {desc}")
        p(f"")
        p(f"**Разбиение в `{target_dir}`:**")
        for mod in modules:
            p(f"  - `{mod}`")
        p("")

    p("---")
    p("")

    # ================================================================
    # ПРИОРИТЕТ 3
    # ================================================================
    p("## 🔵 Приоритет 3: Файлы 600-800 строк (планово)")
    p("")

    priority3_files = [
        ("src/api/endpoints/runs.py", 757),
        ("src/engine/content/segment_chunk_builder_v2.py", 748),
        ("src/workers/run_orchestrator.py", 734),
        ("src/workers/chunk_builder.py", 700),
        ("src/engine/content/clause_tree_builder.py", 682),
        ("src/engine/detectors/llm_detector.py", 678),
        ("src/engine/checks/executor.py", 674),
        ("src/services/export/grid_builder.py", 663),
        ("src/engine/llm/client.py", 660),
        ("src/db/models/document.py", 617),
        ("src/workers/extract_worker.py", 616),
        ("src/api/endpoints/playbooks.py", 615),
        ("src/services/structure/segmenter.py", 610),
        ("src/workers/build_primary_language_source.py", 603),
        ("src/engine/doc_type_checks/loader.py", 598),
    ]

    p("| Файл | Строк | Рекомендация |")
    p("|------|-------|-------------|")
    for filepath, lines in priority3_files:
        name = filepath.split("/")[-1]
        if "endpoint" in filepath or "api/" in filepath:
            rec = "Разбить на sub-routers или выделить сервисный слой"
        elif "worker" in filepath:
            rec = "Выделить бизнес-логику из воркера в сервис"
        elif "model" in filepath:
            rec = "Проверить: возможно, нормально для ORM-модели"
        elif "detector" in filepath or "llm" in filepath:
            rec = "Выделить промпты и парсинг ответов в отдельные модули"
        elif "builder" in filepath:
            rec = "Выделить вспомогательные функции и модели"
        elif "export" in filepath:
            rec = "Разделить по типам экспорта"
        else:
            rec = "Ревью структуры, выделить хелперы"
        p(f"| `{name}` | {lines} | {rec} |")

    p("")
    p("---")
    p("")

    # ================================================================
    # ПРИОРИТЕТ 4
    # ================================================================
    p("## ⚪ Приоритет 4: Файлы 500-600 строк (по возможности)")
    p("")

    priority4_files = [
        ("src/services/relations/detector.py", 584),
        ("src/db/repositories/result_repo.py", 584),
        ("src/workers/check_runner_worker.py", 579),
        ("src/workers/structure_builder.py", 567),
        ("src/workers/convert_worker.py", 548),
        ("src/services/primary_pdf_builder.py", 531),
        ("src/services/export/models.py", 522),
        ("src/services/structure/models.py", 520),
        ("src/db/repositories/document_repo.py", 520),
        ("src/services/export/aggregator.py", 516),
        ("src/core/playbooks/compiler.py", 510),
        ("src/workers/pii_sanitizer.py", 509),
        ("src/services/structure/hierarchy_builder.py", 509),
        ("src/engine/detectors/extraction_llm_detector.py", 509),
    ]

    p("Эти файлы находятся на границе и могут подождать:")
    p("")
    for filepath, lines in priority4_files:
        name = filepath.split("/")[-1]
        p(f"- `{name}` ({lines} строк)")
    p("")
    p("**Для `models.py` файлов (520+ строк):** Это часто нормально,")
    p("если содержат только модели/схемы данных без бизнес-логики.")
    p("Ревью по необходимости.")
    p("")
    p("---")
    p("")

    # ================================================================
    # ОБЩИЕ ПАТТЕРНЫ
    # ================================================================
    p("## 📐 Общие антипаттерны, обнаруженные в проекте")
    p("")
    p("### 1. Дублирование хелперов")
    p("")
    p("`_normalize_uid()` встречается **3 раза** в `document_pipeline_view_service.py`")
    p("(строки 712, 1355, 1571). `_chunk_sort_key()` — **2 раза** (строки 748, 1609).")
    p("")
    p("**Решение:** Вынести в `normalizers.py` один раз.")
    p("")
    p("### 2. Workers содержат бизнес-логику")
    p("")
    p("Файлы в `src/workers/` (chunk_builder 700, run_orchestrator 734,")
    p("extract_worker 616) содержат бизнес-логику вместе с Celery-обёрткой.")
    p("")
    p("**Решение:** Worker должен быть тонким — вызывать сервис.")
    p("```python")
    p("# workers/chunk_builder.py — ПОСЛЕ")
    p("@celery_app.task")
    p("def build_chunks(doc_id):")
    p("    service = ChunkBuildingService()")
    p("    return service.build(doc_id)")
    p("```")
    p("")
    p("### 3. API endpoints с бизнес-логикой")
    p("")
    p("`runs.py` (757 строк), `playbooks.py` (615 строк) содержат")
    p("бизнес-логику прямо в эндпоинтах.")
    p("")
    p("**Решение:** Вынести в сервисный слой, эндпоинт — только")
    p("валидация → вызов сервиса → маппинг ответа.")
    p("")
    p("### 4. ORM-модель как хранилище логики")
    p("")
    p("`document.py` (617 строк) — модель с бизнес-логикой.")
    p("")
    p("**Решение:** Выделить доменную логику в отдельный модуль,")
    p("ORM-модель — только колонки и relationships.")
    p("")
    p("---")
    p("")

    # ================================================================
    # ПОРЯДОК ДЕЙСТВИЙ
    # ================================================================
    p("## 📋 Рекомендуемый порядок действий")
    p("")
    p("### Неделя 1: God-классы")
    p("1. ✅ Разбить `document_pipeline_view_service.py` → `services/pipeline_view/`")
    p("2. ✅ Разбить `checks_runner.py` → расширить `engine/checks/`")
    p("3. ✅ Написать/обновить тесты для обоих")
    p("")
    p("### Неделя 2: Приоритет 2 (верхняя половина)")
    p("4. Разбить `hybrid_classifier.py`")
    p("5. Разбить `chunk_snapshot_builder.py`")
    p("6. Разбить `layout_language_filter.py`")
    p("")
    p("### Неделя 3: Приоритет 2 (нижняя половина) + Workers")
    p("7. Разбить `document_content_service.py`")
    p("8. Разбить `pipeline.py` (structure)")
    p("9. Вынести бизнес-логику из workers")
    p("")
    p("### Неделя 4: Приоритет 3 (по необходимости)")
    p("10. API endpoints → сервисный слой")
    p("11. Оставшиеся файлы по мере касания")
    p("")
    p("---")
    p("")

    # ================================================================
    # МЕТРИКИ УСПЕХА
    # ================================================================
    p("## 📊 Метрики успеха")
    p("")
    p("| Метрика | Сейчас | Цель |")
    p("|---------|--------|------|")
    p("| Файлов > 500 строк | 37 | ≤ 10 |")
    p("| Файлов > 800 строк | 12 | 0 |")
    p("| Максимальный файл | 2242 строк | ≤ 500 строк |")
    p("| Файлов, требующих рефакторинга | 179 | ≤ 50 |")
    p("")
    p("---")
    p("")
    p(f"*Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    return "\n".join(plan)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plan = generate_plan()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(plan)

    print(f"✅ План рефакторинга сохранён: {OUTPUT_FILE}")
    print()
    print("📊 Краткая сводка:")
    print("   🔴 Приоритет 1: 2 God-класса (2242 + 1211 строк)")
    print("   🟡 Приоритет 2: 6 файлов 800-1200 строк")
    print("   🔵 Приоритет 3: 15 файлов 600-800 строк")
    print("   ⚪ Приоритет 4: 14 файлов 500-600 строк")
    print()
    print("   Рекомендуемый старт: document_pipeline_view_service.py")
    print("   Причина: read-only сервис, низкий риск, максимальный эффект")


if __name__ == "__main__":
    main()
    