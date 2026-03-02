"""
Демонстрация пути land_subject_extraction через систему.

Показывает:
1. Что попадает в check_results из Stage 8
2. Как Aggregator это обрабатывает
3. Где это появляется в Excel/Word
"""

from src.services.export.aggregator import aggregate_results
from src.services.export.grid_builder import build_grid_excel
from src.services.export.report_builder import build_report_docx
from src.services.export.summary_builder import build_summary_excel

# Имитация результата Stage 8 (CheckRunner + ValidationEngine)
CHECK_RESULTS = [
    {
        "check_id": "land_subject_extraction",
        "check_name": "Извлечение данных земельного участка",
        "result": "fail",  # category = not_found
        "severity": "high",
        "value_text": "Категория земли: не указана. Площадь: 1500 кв.м. Кадастровый номер: 77:01:0001001:1",
        "confidence": 0.85,
        "detector_used": "rules",
        "quality_flags": {},
        "qc_status": "pending",
        "document_id": "doc-land-001",
        "page": 2,
        "clause_uid": "1.2",
        # Stage 8 — structured_data из structured_extraction
        "structured_data": {
            "cadastral_number": "77:01:0001001:1",
            "area": "1500 кв.м",
            "category": "not_found",  # ← триггер для fail
        },
        # Stage 8 — conditional check triggered
        "conditional_check_triggered": True,
        "trigger_name": "land_plot_trigger",
    },
]

DOCUMENTS = {
    "doc-land-001": {
        "name": "Договор_купли_продажи_земли.docx",
        "folder_path": "/deal/real_estate",
        "doc_type": "contract_real_estate",
        "status": "active",
        "classification_level": "L3",
        "classification_confidence": 0.87,
        "applicable_triggers": ["land_plot_trigger", "re_encumbrance"],
    },
}


def main():
    print("=" * 80)
    print("DEMO: land_subject_extraction в финальных отчётах")
    print("=" * 80)

    # Шаг 1: Aggregator собирает данные
    print("\n[1] Aggregator обрабатывает check_results...")
    agg = aggregate_results(
        deal_id="deal-demo",
        deal_name="Демо-сделка",
        run_id="run-demo-001",
        check_results=CHECK_RESULTS,
        documents=DOCUMENTS,
    )

    print(f"   ✓ Всего проверок: {agg.total_checks}")
    print(f"   ✓ Severity counts: {agg.severity_counts.to_dict()}")
    print(f"   ✓ Условных проверок: {agg.conditional_checks_total}")
    print(f"   ✓ Извлечённых значений: {len(agg.structured_value_rows)}")

    # Шаг 2: Где land_subject_extraction появляется в ExportRow
    print("\n[2] ExportRow (DD Grid):")
    for row in agg.rows:
        if row.check_id == "land_subject_extraction":
            print(f"   Документ: {row.document_name}")
            print(f"   Тип документа: {row.doc_type}")
            print(f"   Проверка: {row.check_name}")
            print(f"   Результат: {row.result} / {row.severity}")
            print(f"   Evidence: {row.evidence_snippet}")
            print(f"   Structured data preview: {row.structured_data_preview}")
            print(f"   Условная проверка: {row.conditional_check_triggered}")
            print(f"   Триггер: {row.trigger_name}")
            print(f"   Уровень классификации: {row.classification_level}")
            print(f"   Confidence классификации: {row.classification_confidence:.0%}")

    # Шаг 3: ConditionalCheckRow (лист Conditional Checks)
    print("\n[3] ConditionalCheckRow (Conditional Checks sheet):")
    for cr in agg.conditional_rows:
        if cr.check_id == "land_subject_extraction":
            print(f"   Документ: {cr.document_name}")
            print(f"   Триггер: {cr.trigger_name}")
            print(f"   Проверка: {cr.check_name}")
            print(f"   Результат: {cr.result} / {cr.severity}")
            print(f"   Evidence: {cr.evidence_snippet}")

    # Шаг 4: StructuredValueRow (лист Extracted Values)
    print("\n[4] StructuredValueRow (Extracted Values sheet):")
    for sv in agg.structured_value_rows:
        if sv.check_name == "Извлечение данных земельного участка":
            print(f"   Документ: {sv.document_name}")
            print(f"   Поле: {sv.field_name}")
            print(f"   Значение: {sv.field_value}")
            print(f"   Формат: {sv.field_format}")
            print(f"   Страница: {sv.page}")

    # Шаг 5: TopRisk (лист Top Risks)
    print("\n[5] TopRisk (Top Risks sheet):")
    for risk in agg.top_risks:
        if risk.check_id == "land_subject_extraction":
            print(f"   Severity: {risk.severity}")
            print(f"   Проверка: {risk.check_name}")
            print(f"   Документ: {risk.document_name}")
            print(f"   Evidence: {risk.evidence_snippet}")
            print(f"   Structured data: {risk.structured_data}")
            print(f"   Условная проверка: {risk.conditional_check_triggered}")
            print(f"   Триггер: {risk.trigger_name}")

    # Шаг 6: DDRequest (лист Request List + Appendix A в Word)
    print("\n[6] DDRequest (Request List sheet + Word Appendix A):")
    for req in agg.dd_requests:
        if req.check_id == "land_subject_extraction":
            print(f"   Priority: {req.priority}")
            print(f"   Check: {req.check_name}")
            print(f"   Адресат: {req.addressee}")
            print(f"   Текст запроса: {req.text[:150]}...")
            print(f"   Документы: {req.document_names}")
            print(f"   Типы документов: {req.doc_types}")

    # Шаг 7: DocTypeSummary (лист By Doc Type)
    print("\n[7] DocTypeSummary (By Doc Type sheet):")
    for summary in agg.doc_type_summaries:
        if summary.doc_type == "contract_real_estate":
            print(f"   Тип документа: {summary.doc_type}")
            print(f"   Документов: {summary.document_count}")
            print(f"   Проверок: {summary.check_count}")
            print(f"   High: {summary.high}")
            print(f"   Avg classification confidence: {summary.avg_classification_confidence:.0%}")
            print(f"   Условных проверок (fail): {summary.conditional_checks_triggered}")

    # Шаг 8: Создание файлов (опционально)
    print("\n[8] Генерация файлов...")
    import os

    os.makedirs("/tmp/land_demo", exist_ok=True)

    grid_data = build_grid_excel(agg)
    with open("/tmp/land_demo/DD_Grid.xlsx", "wb") as f:
        f.write(grid_data)
    print("   ✓ DD_Grid.xlsx → /tmp/land_demo/DD_Grid.xlsx")

    summary_data = build_summary_excel(agg)
    with open("/tmp/land_demo/DD_Summary.xlsx", "wb") as f:
        f.write(summary_data)
    print("   ✓ DD_Summary.xlsx → /tmp/land_demo/DD_Summary.xlsx")

    report_data = build_report_docx(agg, playbook_profile="MA Russia DD")
    with open("/tmp/land_demo/DD_Report.docx", "wb") as f:
        f.write(report_data)
    print("   ✓ DD_Report.docx → /tmp/land_demo/DD_Report.docx")

    print("\n" + "=" * 80)
    print("✅ Готово! Откройте файлы в /tmp/land_demo/ для просмотра.")
    print("=" * 80)


def test_land_subject_extraction_flow():
    """Демонстрация пути land_subject_extraction через систему."""
    main()
