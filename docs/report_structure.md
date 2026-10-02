# DD Report — Целевая структура (v1)

**Статус:** источник истины для `report_builder.py`, `fact_bundle.py`, LLM-промтов и UI.
**Дата:** 2026-10-01
**Основа:** Olswang "Limited Exceptions Only Legal DD Report" + Clifford Chance методология.

---

## 0. Принципы

1. **By-exception.** Отчёт показывает только исключения и материальные вопросы, не весь массив проверок.
2. **Двухуровневая модель.** Global checks (применимы ко всем документам) + doc-type checks (привязаны к типу документа).
3. **Issue | Comments | Recommendation** — ключевая единица детального отчёта.
4. **Executive level за 5 минут, working level за 30 минут.**
5. **Каждый факт — из `check_results`.** LLM переформулирует, но не выдумывает.
6. **Landscape** — для широких таблиц. **Portrait** — для текста.
7. **Reproducibility** — playbook version, run_id, detector coverage фиксируются в Appendix B.

---

## 1. Верхнеуровневая структура документа

```
[PORTRAIT]  Титульная страница
[PORTRAIT]  Оглавление (TOC)
[PORTRAIT]  1. Definitions
[PORTRAIT]  2. Purpose of Report
[PORTRAIT]  3. Terms of Reference
[PORTRAIT]  4. Key Findings / Executive Summary
[LANDSCAPE] 5. Detailed Report
[LANDSCAPE] 6. Extracted Values
[LANDSCAPE] Appendix A. Request List
[PORTRAIT]  Appendix B. Methodology & Reproducibility
[PORTRAIT]  Appendix C. Documents Reviewed
```

---

## 2. Раздел 1. Definitions

### Что выводим

Список сокращений, используемых в отчёте: Buyer, Seller, Target, Company, Group, SPA, Completion, Data Room, Report.

### Источник данных

- `meta.playbook_profile` → шаблон словаря по профилю (например, "M&A Russia DD").
- Если в playbook есть секция `definitions:` — берём оттуда.
- Иначе — hardcoded template для M&A Russia DD.

### Что даёт LLM

Ничего. Definitions — шаблонный блок, не narrative.

### Пример

```
"Buyer" means [Buyer Name].
"Company" means [Target Name].
"Completion" means completion of the Acquisition pursuant to the terms of the SPA.
"Data Room" means the electronic data site hosted by [Provider] created for the purposes of the Acquisition.
"Group" means the Company and each of its Subsidiaries.
"Report" means this 'exceptions only' legal due diligence report.
"SPA" means the share purchase agreement to be entered into between the Seller and the Buyer.
```

---

## 3. Раздел 2. Purpose of Report

### Что выводим

3–5 предложений: зачем этот отчёт, в каком формате он подготовлен, что он покрывает и что не покрывает.

### Источник данных

- `meta.playbook_profile`
- `meta.checks_mode` (strict / balanced / fast)
- `totals.documents`
- `totals.checks_completed`

### Что даёт LLM

**Да.** Промт `purpose_of_report.md`.

### Пример

```
This Report summarises the results of our legal due diligence exercise 
on an "exceptions only" basis. We reviewed 2 documents and performed 
34 checks (10 global + 24 document-type). The Report highlights only 
material issues which we believe should be drawn to the Buyer's 
attention, either because we recommend a provision in the SPA or because 
we recommend certain action by the parties prior to, on, or after Completion.
```

---

## 4. Раздел 3. Terms of Reference

### 3.1. Scope

**Что выводим:** что проверяли (области права, типы документов).

**Источник:** `meta.playbook_profile`, `meta.checks_mode`, `totals`.

**LLM:** да, 1–2 предложения.

**Пример:** "Our review was limited to matters of Russian law as applied to the documents provided in the Data Room."

### 3.2. Exclusions

**Что выводим:** что не проверяли.

**Источник:** playbook `excluded_areas: ["Tax", "Environmental", "Insurance"]`.

**LLM:** да, 1 предложение.

**Пример:** "We did not review tax, environmental, or insurance matters."

### 3.3. Limitations

**Что выводим:** ограничения ответственности и методологические оговорки.

**Источник:** `quality.low_confidence_count`, `quality.needs_manual_review_count`, `meta.checks_mode`.

**LLM:** да, 2–3 предложения.

**Пример:** "Findings based on low-confidence extraction should be manually verified. We express no opinion as to matters of fact."

### 3.4. Assumptions

**Что выводим:** допущения (документы аутентичны, не проверяли факты).

**Источник:** hardcoded template.

**LLM:** да, 1 абзац.

**Пример:** "We have assumed that all documents provided are true, complete, and up-to-date copies of the originals."

---

## 5. Раздел 4. Key Findings / Executive Summary

### 4.1. Overall Summary

**Что выводим:** 3–5 предложений общей сводки.

**Источник (`summary_builder`):**
- `_count_severity(check_results)` → totals
- `_count_quality_metrics(check_results, documents)` → quality
- `_build_doc_type_summaries(check_results, documents)` → doc-type breakdown

**Payload для LLM:**
```python
{
  "meta": {"deal_name", "run_id", "playbook_version", "generated_at"},
  "totals": {"documents", "checks_planned", "checks_completed",
             "checks_not_applicable", "critical", "high", "medium",
             "pass", "unclear"},
  "global": {"checks": 10, "issues": 0},
  "doc_type": [
    {"doc_type": "credit_agreement", "check_count": 12,
     "critical": 0, "high": 2, "medium": 3, "pass": 7},
    ...
  ],
}
```

**Промт:** `overall_summary.md`.

**Пример:**
```
We reviewed 2 documents and performed 34 checks (10 global + 24 
document-type). No critical or high-risk issues were identified. 
All checks passed. The analysis is based on the documents available 
in the Data Room as at 01 October 2026.
```

### 4.2. Global Checks Summary

**Что выводим:**
1. Сводная таблица: `Global Check | Docs Checked | Issues | Critical | High | Medium | Pass`.
2. Narrative по каждому чеку с issues (1–2 предложения).

**Источник (`fact_bundle`):**
- `_split_by_scope()` → `global_rows`
- `_group_by_check(global_rows)` → `by_check`

**Payload для LLM (по каждому чеку):**
```python
{
  "check_id": "coc_check",
  "check_name": "Change of Control Clause",
  "documents_checked": 2,
  "issues": 1,
  "critical": 0, "high": 1, "medium": 0, "pass": 1,
  "top_evidence": "«any event or circumstance where 50% or more...»",
  "affected_documents": ["BoS Facility Agreement"],
}
```

**Промт:** `global_by_check_summary.md`.

**Пример narrative:** "Change of Control: 1 high-risk finding in BoS Facility Agreement (clause 4.2.2). Other documents do not contain change of control clauses."

### 4.3. Document-Type Checks Summary

**Что выводим:**
1. Для каждого doc_type: LLM narrative (2–3 предложения).
2. Для каждого doc_type: таблица `Check | Docs Checked | Issues | Critical | High | Medium | Pass`.

**Источник (`summary_builder._build_doc_type_summaries`):**
```python
[{
  "doc_type": "credit_agreement",
  "document_count": 2,
  "check_count": 12,
  "critical": 0, "high": 2, "medium": 3, "pass": 7, "unclear": 0,
  "avg_classification_confidence": 0.87,
  "low_confidence_count": 0,
  "conditional_checks_triggered": 2,
}]
```

**Промт:** `doc_type_summary.md`.

**Пример:** "Credit Agreements (2 documents): 12 document-type checks performed. 2 high-risk issues: change of control clause (BoS) and security restrictions (HSBC). Both require waivers before Completion."

---

## 6. Раздел 5. Detailed Report

### 5.1. Global Checks Table

**Что выводим:** таблица, одна строка на (global check × document).

**Колонки:**
`Check | Document | Result | Severity | Clause | Issue | Comments | Recommendation`

**Источник данных (per row):**
- `check_results`: `check_id`, `document_id`, `result`, `severity`, `clause_uid`, `page`, `display_text`, `review_message`, `review_status`, `confidence`.
- `check_def`: `name`, `description`, `origin`, `ui_mode`.
- `documents[doc_id]`: `filename`, `doc_type`, `folder_path`, `language`.
- `EvidenceBundle`: `primary_units[0].text`, `cross_refs`.
- `dd_request_templates[check_id].text` — шаблон recommendation.

**Payload для LLM (per row):**
```python
{
  "check_id": "credit.coc",
  "check_name": "Change of Control Clause",
  "description": "...",
  "origin": "DOCUMENT_TYPE",
  "doc_type": "credit_agreement",
  "ui_mode": "risk_detection",
  "severity": "high",
  "result": "fail",
  "review_status": "clause_defined",
  "review_message": "...",
  "display_text": "...",
  "confidence": 0.87,
  "document_name": "BoS Facility Agreement",
  "document_folder": "01. Key Agreements",
  "clause_uid": "4.2.2",
  "page": 12,
  "evidence_text": "«any event or circumstance where 50% or more...»",
  "cross_refs": ["4.2.3", "9.1"],
  "structured_data": {...},
  "recommendation_template": "...",
}
```

**Промт:** `issue_comments_recommendation.md`.

**Выход LLM (per row):**
```json
{
  "issue": "Change of control clause in BoS Facility Agreement (clause 4.2.2).",
  "comments": "On change of control, BoS may cancel commitments and demand repayment.",
  "recommendation": "Obtain waiver from BoS prior to Completion."
}
```

### 5.2. Document-Type Checks Table

**Что выводим:** для каждого doc_type — отдельная секция. Для каждого документа — таблица.

**Структура:**
```
5.2.1 Credit Agreements
  5.2.1.1 BoS Facility Agreement (Credit Agreement)
    Columns: Check | Result | Severity | Clause | Issue | Comments | Recommendation
  5.2.1.2 HSBC Facility Agreement (Credit Agreement)
  5.2.2 Supply Contracts
  5.2.2.1 Booker Supply Contract
```

**Источник (`fact_bundle`):**
- `_split_by_scope()` → `doc_type_rows_by_type`
- `_group_by_check(doc_type_rows)` → `by_check`
- `_group_by_document(doc_type_rows)` → `by_document`

**Payload:** тот же, что 5.1.

**Промт:** тот же `issue_comments_recommendation.md`.

---

## 7. Раздел 6. Extracted Values

**Что выводим:** таблица извлечённых значений.

**Колонки:** `Document | Doc Type | Field | Value | Clause | Page`.

**Источник (`report_builder._get_extracted_values`):**
```python
[{
  "document_name": "BoS Facility Agreement",
  "doc_type": "credit_agreement",
  "field_name": "lender_status_display",
  "field_value": "Банк (лицензия ЦБ РФ № 1481)",
  "clause_uid": "1.1",
  "page": 3,
}]
```

**LLM (опционально):** 1–2 предложения summary перед таблицей.

**Промт:** `extracted_values_summary.md`.

---

## 8. Appendix A. Request List

**Что выводим:** таблица DD-запросов.

**Колонки:** `# | Priority | Check | Text | Addressee | Documents`.

**Источник (`report_builder._build_dd_requests_for_report`):**
```python
[{
  "priority": "critical",
  "check_name": "Change of Control Clause",
  "addressee": "Кредитор / Юридический советник",
  "text": "Просим уточнить в {doc_names}: определение смены контроля...",
  "document_count": 2,
  "document_names": ["BoS Facility Agreement", "HSBC Facility Agreement"],
}]
```

**LLM (опционально):** 1–2 предложения summary перед таблицей.

**Промт:** `requests_summary.md`.

---

## 9. Appendix B. Methodology & Reproducibility

**Что выводим:**
- Playbook version, profile.
- Checks mode, pipeline strategy.
- Environment hash.
- Run ID.
- Generated at.
- Total checks, completed, not_applicable.
- Detector coverage: rules_based / hybrid / llm_based.
- Avg confidence, evidence validity rate.
- LLM narrative (1 абзац).

**Источник:**
- `meta.*` — playbook, run_id, environment.
- `quality.*` — confidence, validity, detector breakdown.

**Промт:** `methodology.md`.

---

## 10. Appendix C. Documents Reviewed

**Что выводим:** таблица документов.

**Колонки:** `Filename | Folder | Doc Type | Language | Pages | SHA256 | Reviewed`.

**Источник (`documents` dict):**
```python
[{
  "filename": "BoS_Facility_Agreement.pdf",
  "folder_path": "01. Key Agreements",
  "doc_type": "credit_agreement",
  "language": "EN",
  "page_count": 45,
  "sha256_file": "abc123...",
  "reviewed_by_person": False,
}]
```

**LLM:** нет. Чистая таблица.

---

## 11. LLM Narratives — полный список

| Narrative | Промт | Раздел | Приоритет |
|---|---|---|---|
| Purpose of Report | `purpose_of_report.md` | 2 | 🟢 |
| Terms of Reference | `terms_of_reference.md` | 3 | 🟡 |
| Overall Summary | `overall_summary.md` | 4.1 | 🔴 |
| Global by Check | `global_by_check_summary.md` | 4.2 | 🔴 |
| Doc-Type Summary | `doc_type_summary.md` | 4.3 | 🔴 |
| Issue/Comments/Recommendation | `issue_comments_recommendation.md` | 5.1 + 5.2 | 🔴 |
| Extracted Values intro | `extracted_values_summary.md` | 6 | 🟢 |
| Requests intro | `requests_summary.md` | A | 🟢 |
| Methodology | `methodology.md` | B | 🟢 |

**Приоритетные 4 промта** дают 80% качества.

---

## 12. Маппинг: раздел → источник данных

| Раздел | Источник | Статус |
|---|---|---|
| Титульная | `meta` | 🟡 требует `buyer_name`, `target_name`, `generated_at` |
| TOC | Word field | ✅ |
| Definitions | playbook / template | 🟡 |
| Purpose | `meta` + LLM | 🟡 |
| Terms of Reference | playbook + LLM | 🟡 требует `excluded_areas` |
| Overall Summary | `_count_severity` + LLM | ✅ |
| Global Summary | `_split_by_scope` + `_group_by_check` + LLM | 🟡 требует `_split_by_scope` |
| Doc-Type Summary | `_build_doc_type_summaries` + LLM | ✅ |
| Detailed Report | `check_results` + `check_def` + `EvidenceBundle` + LLM | 🟡 требует промт |
| Extracted Values | `_get_extracted_values` | ✅ |
| Requests | `_build_dd_requests_for_report` | ✅ |
| Methodology | `meta` + `quality` | ✅ |
| Documents Reviewed | `documents` | ✅ |

---

## 13. Порядок реализации

| # | Шаг | Выход | Приоритет |
|---|---|---|---|
| 1 | Зафиксировать эту структуру | `docs/report_structure.md` | 🔴 |
| 2 | Собрать `fact_bundle.py` | Модуль с `_split_by_scope`, `_group_by_check`, `by_document`, `by_priority` | 🔴 |
| 3 | Рефакторинг `report_builder.py` — сигнатура | `build_report_docx(fact_bundle, narratives, style)` | 🔴 |
| 4 | 4 приоритетных промта | `overall_summary.md`, `global_by_check_summary.md`, `doc_type_summary.md`, `issue_comments_recommendation.md` | 🔴 |
| 5 | `llm_narratives.py` | Сервис вызова LLM | 🔴 |
| 6 | Скелет новых секций в `report_builder.py` | Definitions / Purpose / Terms / Key Findings / Detailed | 🟡 |
| 7 | Landscape + титульная + TOC | Layout | 🟡 |
| 8 | Humanize enums + hide `__preamble__` | i18n | 🟡 |
| 9 | Стили (corporate_blue / legal_serif / modern_minimal) | UI dropdown | 🟢 |
| 10 | Графики (matplotlib) | Severity pie, findings by doc | 🟢 |
| 11 | PDF (soffice) | `--convert-to pdf` | 🟢 |


