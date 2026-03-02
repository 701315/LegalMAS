"""
Тестовые фикстуры для Aggregator и Exporter (Stage 9).

Используются в:
- tests/unit/test_aggregator.py
- tests/unit/test_exporters.py
"""

SAMPLE_CHECK_RESULTS_V9 = [
    {
        "check_id": "coc_001",
        "check_name": "Change of Control",
        "result": "fail",
        "severity": "critical",
        "value_text": "Согласие контрагента на смену контроля не предусмотрено.",
        "confidence": 0.92,
        "detector_used": "rules",
        "quality_flags": {},
        "qc_status": "pending",
        "document_id": "doc-001",
        "page": 5,
        "clause_uid": "3.1",
        # Stage 8 поля
        "structured_data": {},
        "conditional_check_triggered": False,
        "trigger_name": "",
    },
    {
        "check_id": "land_subject_extraction",
        "check_name": "Извлечение данных земельного участка",
        "result": "fail",
        "severity": "high",
        "value_text": "Категория земли не указана.",
        "confidence": 0.85,
        "detector_used": "rules",
        "quality_flags": {},
        "qc_status": "pending",
        "document_id": "doc-002",
        "page": 2,
        "clause_uid": "1.2",
        "structured_data": {
            "cadastral_number": "77:01:0001001:1",
            "area": "1500 кв.м",
            "category": "not_found",
        },
        "conditional_check_triggered": True,
        "trigger_name": "land_plot_trigger",
    },
    {
        "check_id": "consent_001",
        "check_name": "Third Party Consents",
        "result": "pass",
        "severity": "high",
        "value_text": "Все согласия получены.",
        "confidence": 0.88,
        "detector_used": "hybrid",
        "quality_flags": {},
        "qc_status": "ok",
        "document_id": "doc-001",
        "page": 7,
        "clause_uid": "4.2",
        "structured_data": {},
        "conditional_check_triggered": False,
        "trigger_name": "",
    },
]

SAMPLE_DOCUMENTS_V9 = {
    "doc-001": {
        "name": "Договор_купли_продажи_акций.docx",
        "folder_path": "/deal/contracts",
        "doc_type": "contract_spa",
        "status": "active",
        "classification_level": "L2",
        "classification_confidence": 0.91,
        "applicable_triggers": ["coc", "consent"],
    },
    "doc-002": {
        "name": "Договор_купли_продажи_земли.docx",
        "folder_path": "/deal/real_estate",
        "doc_type": "contract_real_estate",
        "status": "active",
        "classification_level": "L3",
        "classification_confidence": 0.87,
        "applicable_triggers": ["land_plot_trigger", "re_encumbrance"],
    },
}
