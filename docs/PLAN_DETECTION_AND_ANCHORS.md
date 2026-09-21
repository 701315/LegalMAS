# PLAN: Detection Audit + Anchor Refactoring

**Source:** полный план согласован в диалоге, v2.0 (consolidated)
**Started:** 2026-09-21
**Last updated:** 2026-09-21 (после B1.1 + verified runtime)
**Master HEAD:** `ec7db44`

## Track B: Anchor & Location

| Этап | Статус | Commit | Tag | Notes |
|---|---|---|---|---|
| B0.1 — sized-chunks clause_uids/raw_uids | ✅ DONE | `a1a3f0d` / merge `64e1b57` | `pre-B0.1-20260921-042922` / `post-B0.1-20260921-043501` | API отдаёт `clause_uids` + `raw_uids`. Verified: 97 chunks, 0 пустых clause_uids |
| B0.2 — element_id (layout UUID) + chunk_id (canonical) | ✅ DONE | `969ca8b` / merge `571c622` | `pre-B0.2-20260921-045259` / `post-B0.2-20260921-072244` | Verified: 13/13 element_id = `ru:node:N:NNNN`. Unit-тесты 6 PASSED (`b3533d0`). Ограничение: legal_unit chunk_id = compound, defer to B1 |
| B0.2b Phase 1 — location_source enum + clause_ref derive | ✅ DONE | `407684f` / merge `4e4bf45` | `pre-B0.2b-20260921-075754` / `post-B0.2b-20260921-111115` | Verified run `b2a5a24e`: 136 canonical_check + 12 per_field + 1 none |
| B0.3 — location only for positive findings | ✅ DONE | merge `a285b84` | `pre-B0.3-20260921-135411` / `post-B0.3-20260921-135450` | `_is_positive_location_finding` + Rule 1b в `_build_cell_value`. Универсальный whitelist `(ui_mode, review_status)`. Legacy `review_status=None` сохраняет cell_state-семантику. `unclear` сохранён как manual-review aid. Live-verified: CoC → `location_source="none"`, positive ячейки → `canonical_check`/`per_field`. Regression diff пустой (29 предсуществующих failures не связаны) |
| B0.4 — bbox_union в snapshot chunks + проброс в CheckResult | ✅ DONE | `85301d6` + `57bdce6` / merge `d7a3851` + `49fa9e9` | `pre-B0.4-20260921-144231` / `post-B0.4-20260921-145648`, `pre-B0.4b-20260921-153256` / `post-B0.4b-20260921-153523` | `_build_element_bbox_map` + `_compute_bbox_union` в `segment_chunk_builder_v2.py` → `meta["bbox_union"]` per chunk (page-matched union, multi-page fallback). B0.4b: проброс через `extraction_contexts` whitelist в executor. `CheckResult.bbox = {"union": [x0,top,x1,bottom], "page": N, "element_ids": [...]}`. Universal: any doc / check / ui_mode. Live-verified run `ec692954`: **34/34 filled** (0 null). CoC → `[85.15, 304.95, 572.45, 380.38]` (page 4), control → `[85.15, 278.5, 572.4, 315.98]` (page 1) |
| B0.5 — context_trace.score_breakdown | ✅ DONE | `73ce101` / merge `2632e21` | `pre-B0.5-20260921-160717` / `post-B0.5-20260921-160921` | Проброс top-level `score_breakdown` из retrieval chunk в `extraction_contexts` (executor L1185). `context_trace[i].score_breakdown` = `{bm25_raw, bm25_norm, dense_raw, dense_norm, metadata_raw, metadata_norm, weighted_sparse, weighted_dense, weighted_metadata, combined_score}`. Unit-тесты 4 PASSED. Live-verified run `ef76f962`: все 10 полей; `combined_score` == `score` (0.711 для CoC, 0.877 для control) |
| **B0.6 — DD Grid LOCATION → viewer page mismatch (frontend)** | ⏳ TODO | — | — | Клик на «p. 4 · cl. 7.2» открывает page 1 с подсветкой cl. 1.1. Backend отдаёт корректные `location_page`/`location_clause_uid` (verified live). Баг во frontend: payload от DD Grid → modal или `useEffect` в `DocumentViewerModal.tsx`. Backend не трогаем, worker restart не нужен |
| B1 — Canonical Anchor Contract | ⏳ TODO | — | — | Pydantic `CheckAnchor` + ORM + миграция + `citation_resolver` + рефакторинг 3 детекторов + persistence. Sanitize structural markers — уже в B1.1 (DONE). Fix legal_unit chunk_id, удаление legacy DTO (`has_location_fallback`, `location_fallback_reason`) |
| B1.1 — Sanitize structural markers in location_clause_ref | ✅ DONE | `3f5d972` / merge `ec7db44` | `pre-B1.1-20260921-164938` / `post-B1.1-20260921-165202` | `_is_structural_marker` (regex `^__[a-z][a-z0-9_]*__$`) + sanitize в `_normalize_location_bundle` — единая точка всех источников (per_field / display_text / canonical_check). `_derive_clause_ref_from_uid` расширен с узкой проверки `__preamble__` на общий предикат. Универсально: `__preamble__`, `__metadata__`, `__header__`, `__intro__` и любые будущие `__[a-z]+__`. Unit-тесты 20 PASSED, regression diff пустой. Runtime-verified: `__preamble__` → `None`, control `"п. 7.2"` → `"п. 7.2"` |
| B2 — Citation Resolver | ⏳ TODO | — | — | `resolve_quote_in_source`: exact_span → fuzzy_span → clause_only → page_only → none |
| B3 — Citation Extraction | ⏳ TODO | — | — | Обогатить `field_extraction` / `risk_detection` / `rules_only` + executor |
| B4 — Persistence Layer | ⏳ TODO | — | — | `check_result_anchor_repo` + денормализация primary anchor |
| B5 — API + Frontend | ⏳ TODO | — | — | `primary_anchor` в `_provenance_dict`, layoutElementIds в viewer payload |

## Track A: Detection Quality Audit

| Этап | Статус | Commit | Notes |
|---|---|---|---|
| A0 — presence_signal для field_extraction | ✅ DONE | merge `04fd7f5` | См. раздел «A0 — детали» ниже |
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
609590e feat(playbook): add PresenceSignalConfig, field, and validators
ca1a51b feat(executor): reconcile field_extraction result via presence_signal
4a28e79 chore(playbooks): declare presence_signal in coc_change_of_control_regime
689d406 test(playbook): cover presence_signal validation contract
1c2a1fa test(executor): cover presence_signal verdicts and fail-safe
78b6a98 test(executor): cover presence_signal gate end-to-end in field_extraction path
04fd7f5 Merge branch 'feat/A0-presence-signal-contract-v2'


**Теги:** `pre-A0-20260921-114847` / `post-A0-20260921-121546`

**Тесты:** 81 PASSED (15 models + 9 helper + 29 field_extraction + 28 соседних).

**End-to-end verification (run `a3634cc7-94bb-40d9-b293-7a54e7e7bcd1`):**

- `coc_change_of_control_regime`: `result=missing_required_clause`, `review_status=clause_missing`, `severity=high`.
- Playbook version: `ac211b2c-d79e-412a-a6d6-917c89612145` (`playbook 2 (COC new)`), `presence_signal` присутствует в `compiled_checks`.
- Regression: 33 field_extraction чека — все `pass` / `no_issue_detected`, без сдвигов.

**Разблокирует:** B0.3 (location only for positive findings) — выполнено.

## B0.3 — детали

**Проблема:** `_build_cell_value` использовал `cell_state != "defined"` как единственный фильтр для location. Для CoC `cell_state = "defined"` (в колонке есть `coc_display.value`), но `review_status = "clause_missing"` — location показывался для негативной находки.

**Решение (универсальное):**

- Helper `_is_positive_location_finding(ui_mode, review_status) -> bool | None`.
  - `None` — legacy-запись (до B0.2b, `review_status` NULL) → полагаемся только на `cell_state`.
  - `True/False` — по семантическому whitelist.
- Whitelist `_POSITIVE_LOCATION_COMBOS`:
(field_extraction, no_issue_detected), (field_extraction, unclear),
(clause_presence, no_issue_detected), (clause_presence, unclear),
(risk_detection, issue_detected), (risk_detection, unclear),

- Fail-safe: неизвестная комбинация → `False` → location не показывается.
- Rule 1b в `_build_cell_value` (после Rule 1, перед Rule 2) — если `positive is False`, вернуть `CellValueDTO` с `location_source="none"`.

**Файлы:**

- `src/services/dd_grid_v1_builder.py` — helper + Rule 1b.
- `tests/unit/services/test_dd_grid_v1_builder_location.py` — новый файл, 18 PASSED.

**Коммиты:**
594f949 feat(dd-grid): suppress location for negative findings via review_status
a285b84 Merge branch 'feat/B0.3-location-positive-only'


**Теги:** `pre-B0.3-20260921-135411` / `post-B0.3-20260921-135450`

**Live verification (run `a3634cc7`):**

- `coc_change_of_control_regime` → `location_source="none"`, `location_page=null`, `location_clause_ref=null`. `cell_state` остаётся `"defined"` (Rule 1b не трогает cell_state).
- `application_procedure_framework__application_procedure_present_display` → `location_source="canonical_check"`, page 1, п. 1.2 — positive ячейки location сохраняют.
- 33 field_extraction чека — regression diff пустой.

**Не входит в B0.3 (отдельные задачи):** `unclear` сохранён как manual-review aid; unknown `ui_mode`/`review_status` — fail-safe. Sanitize structural markers — отдельно в B1.1.

## Process Rules

Каждый фикс:

1. Pre-tag на `origin/master` (формат: `pre-<stage>-YYYYMMDD-HHMMSS`).
2. Ветка `feat/<stage>-краткое-описание` (или `fix/`, `docs/`, `chore/`).
3. Атомарный commit (Conventional Commits).
4. Push ветки в origin.
5. Тесты (dedicated + regression).
6. Merge `--no-ff` в master.
7. Post-tag (формат: `post-<stage>-YYYYMMDD-HHMMSS`).
8. Удаление ветки локально и на origin.
9. Обновление таблиц в этом файле.

При падении тестов: `git reset --hard <pre-tag>`, `git push --force-with-lease`.

**Regression-verify:** если прогон тестов даёт failures — сравнить список падений с патчем и без патча (`git stash` → pytest → `git stash pop`). Diff должен быть пустым. Если в diff появились новые строки — это регресс, откат.

## Process Rules — Worker Restart

**Критично:** при изменении кода, который выполняется внутри Celery workers, необходим **перезапуск соответствующего worker'а** перед тестами. Backend `uvicorn --reload` покрывает только `src/api/**`.

### Маппинг: код → worker

| Изменённый код | Worker для перезапуска |
|---|---|
| `src/api/**` | backend (uvicorn --reload, авто) |
| `src/engine/checks/**` | **worker-heavy-checks** |
| `src/engine/detectors/**` | **worker-heavy-checks** |
| `src/engine/playbook/**` | **worker-heavy-checks** |
| `src/engine/retrieval/**` | **worker-heavy-checks** |
| `src/engine/content/**` | worker-heavy-enrichment + worker-heavy-checks |
| `src/workers/**`, `src/services/**` | worker-default |
| `src/classifiers/**` | worker-heavy-segment-classification |
| `frontend/**` | frontend (Vite, авто) |

**Активные worker'ы (dev):**

- tmux session `steloom-dev`, окна:
  - `backend` (0), `frontend` (1), `w-default` (2), `w-enrich` (3),
  - `w-segclass` (4), **`w-checks` (5)**, `w-system` (6), `beat` (7), `shell-` (8).
- `worker-heavy-checks` = окно `w-checks`.
- Launcher: `/home/steloom/dev-run/run-with-log.sh <name> /home/steloom/dev-run/worker-checks.sh`.

### Команда рестарта

```bash
# Stop
tmux send-keys -t steloom-dev:w-checks C-c
sleep 10
ps -p $(pgrep -f worker-heavy-checks | head -1) 2>&1

# Start (same launcher as initial)
tmux send-keys -t steloom-dev:w-checks \
  "/home/steloom/dev-run/run-with-log.sh worker-checks /home/steloom/dev-run/worker-checks.sh" Enter
sleep 20

# Verify lstart > commit time
ps -o pid,lstart,cmd -p $(pgrep -f 'worker-heavy-checks' | head -1)
tail -30 /home/steloom/dev-logs/worker-checks.log