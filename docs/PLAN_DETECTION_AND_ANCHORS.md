# PLAN: Detection Audit + Anchor Refactoring

**Source:** полный план согласован в диалоге, v2.0 (consolidated)
**Started:** 2026-09-21
**Last updated:** 2026-09-21 (после A0 v2 + verified end-to-end)
**Master HEAD:** `04fd7f5`

## Track B: Anchor & Location

| Этап | Статус | Commit | Tag | Notes |
|---|---|---|---|---|
| B0.1 — sized-chunks clause_uids/raw_uids | ✅ DONE | `a1a3f0d` / merge `64e1b57` | `pre-B0.1-20260921-042922` / `post-B0.1-20260921-043501` | API отдаёт `clause_uids` + `raw_uids`. Verified: 97 chunks, 0 пустых clause_uids |
| B0.2 — element_id (layout UUID) + chunk_id (canonical) | ✅ DONE | `969ca8b` / merge `571c622` | `pre-B0.2-20260921-045259` / `post-B0.2-20260921-072244` | Verified: 13/13 element_id = `ru:node:N:NNNN`. Unit-тесты 6 PASSED (`b3533d0`). Ограничение: legal_unit chunk_id = compound, defer to B1 |
| B0.2b Phase 1 — location_source enum + clause_ref derive | ✅ DONE | `407684f` / merge `4e4bf45` | `pre-B0.2b-20260921-075754` / `post-B0.2b-20260921-111115` | Verified run `b2a5a24e`: 136 canonical_check + 12 per_field + 1 none |
| B0.2b — DD Grid LOCATION → viewer page mismatch | ⏳ TODO | — | — | Клик на «p. 4 · cl. 7.2» открывает page 1 с подсветкой cl. 1.1. Frontend-баг в передаче payload или в useEffect modal. Аудит frontend DD Grid + DocumentViewerModal |
| B0.2b-followup — sanitize structural markers in location_clause_ref | ⏳ TODO | — | — | Решается в B1 через `CheckAnchor` sanitizer. Пока per_field может отдать `__preamble__` как clause_ref |
| B0.3 — location only for positive findings | ✅ DONE | merge `a285b84` | `pre-B0.3-20260921-135411` / `post-B0.3-20260921-135450` | `_is_positive_location_finding` + Rule 1b в `_build_cell_value`. Универсальный whitelist `(ui_mode, review_status)`. Legacy `review_status=None` сохраняет cell_state-семантику. `unclear` сохранён как manual-review aid. Live-verified: CoC → `location_source="none"`, positive ячейки → `canonical_check`/`per_field`. Regression diff пустой (29 предсуществующих failures не связаны) |
| **B0.4 — CheckResult.bbox from layout** | ⏳ TODO | — | — | Правка в `executor.py::_extract_primary_context_provenance` + `_document_content_chunks.py::normalize_snapshot_chunk_metadata`. Worker restart обязателен |
| **B0.5 — context_trace.score_breakdown** | ⏳ TODO | — | — | Правка в `executor.py::_build_context_provenance_trace`. Worker restart обязателен |
| B1 — Canonical Anchor Contract | ⏳ TODO | — | — | Pydantic `CheckAnchor` + ORM + миграция. Sanitize structural markers + fix legal_unit chunk_id + удаление legacy DTO (`has_location_fallback`, `location_fallback_reason`) |
| B2 — Citation Resolver | ⏳ TODO | — | — | `resolve_quote_in_source`: exact_span → fuzzy_span → clause_only → page_only → none |
| B3 — Citation Extraction | ⏳ TODO | — | — | Обогатить `field_extraction` / `risk_detection` / `rules_only` + executor |
| B4 — Persistence Layer | ⏳ TODO | — | — | `check_result_anchor_repo` + денормализация primary anchor |
| B5 — API + Frontend | ⏳ TODO | — | — | `primary_anchor` в `_provenance_dict`, layoutElementIds в viewer payload |

## Track A: Detection Quality Audit

| Этап | Статус | Commit | Notes |
|---|---|---|---|
| **A0 — presence_signal для field_extraction** | ✅ DONE | merge `04fd7f5` | См. раздел «A0 — детали» ниже |
| A1 — Программный аудит (SQL) | ⏳ TODO | — | Объективный снимок result × review_status × ui_mode. Отчёт `docs/audit/detection_audit_YYYY_MM.md` |
| A2 — Ручной аудит (юрист) | ⏳ TODO | — | Требует юриста. 50 находок, стратификация по check_id. Precision/recall |
| A3 — Аудит YAML | ⏳ TODO | — | Требует юриста + product. Чек-лист по 8 пунктам |
| A4 — Калибровка порогов | ⏳ TODO | — | После A2. `CHECK_PASS_THRESHOLD`, `CHECK_UNCLEAR_THRESHOLD`, grounding-пороги |
| A5 — Улучшение промптов | ⏳ TODO | — | После A2+A3. YAML `llm_prompt_extraction`, few-shot, regression-тест |

## A0 — детали

**Проблема (диагноз, реальная предпосылка):**

Чек `coc_change_of_control_regime` имеет `ui_mode: field_extraction`. В `executor.py` ветка `is_field_extraction` определяла business-result через `_has_meaningful_extraction(structured_data, check)`, которая возвращает `True`, если есть хоть одно meaningful fact-поле. Для CoC таким полем было `coc_display.value = "Положения о смене контроля не установлены"` — полное предложение, не входящее в `NOT_FOUND_VALUES`. Signal-поля (`coc_status = "missing"`, `coc_regime_type = "not_specified"`) отбрасывались как not-found. Результат: `result = "pass"` → `review_status = "no_issue_detected"`, хотя фактически клаузы нет.

Масштаб — 40 check_id с `ui_mode: field_extraction`.

**Решение (универсальное, opt-in):**

Декларативный presence-gate `PresenceSignalConfig` в `ExtractionConfig`:

- Поле `presence_signal: {field, present_values, missing_values, unclear_values}` в YAML.
- Валидация на load: `field` объявлен в `extraction.fields`; группы попарно disjoint; union == `allowed_values(field)`.
- Executor читает значение gate-поля и маппит: `present → pass`, `missing → missing_required_clause`, `unclear → unclear`, `undeclared/not_extracted → unclear` (fail-safe).
- Без `presence_signal` поведение не меняется (regression-safe).

**Файлы:**

- `src/engine/playbook/models.py` — `PresenceSignalConfig`, поле в `ExtractionConfig`, `_validate_presence_signal_contract`, доп. валидатор в `CheckDefinition`.
- `src/engine/checks/executor.py` — helper `_classify_presence_signal` + реконсиляция в ветке `is_field_extraction`.
- `playbooks/global_checks/coc/coc_change_of_control_regime.yaml` — объявление `presence_signal` для `coc_status`.

**Коммиты:**
