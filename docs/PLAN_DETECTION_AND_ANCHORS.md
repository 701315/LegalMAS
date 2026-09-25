# PLAN: Detection Audit + Anchor Refactoring

> ⚠️ **Исторический план до 2026-09-21.**
> Актуальное состояние на 2026-09-25 → см. `docs/HANDOVER_v7.3.md` (v7.3.2).
> Ниже — как было на master HEAD `7c01e38`. Не для старта новых работ.

**Source:** полный план согласован в диалоге, v2.0 (consolidated)
**Started:** 2026-09-21
**Last updated:** 2026-09-21 (после B0.6 + verified browser)
**Master HEAD:** `7c01e38`

## Track B: Anchor & Location

| Этап | Статус | Commit | Tag | Notes |
|---|---|---|---|---|
| B0.1 — sized-chunks clause_uids/raw_uids | ✅ DONE | `a1a3f0d` / merge `64e1b57` | `pre-B0.1-20260921-042922` / `post-B0.1-20260921-043501` | API отдаёт `clause_uids` + `raw_uids`. Verified: 97 chunks, 0 пустых clause_uids |
| B0.2 — element_id (layout UUID) + chunk_id (canonical) | ✅ DONE | `969ca8b` / merge `571c622` | `pre-B0.2-20260921-045259` / `post-B0.2-20260921-072244` | Verified: 13/13 element_id = `ru:node:N:NNNN`. Unit-тесты 6 PASSED (`b3533d0`). Ограничение: legal_unit chunk_id = compound, defer to B1 |
| B0.2b Phase 1 — location_source enum + clause_ref derive | ✅ DONE | `407684f` / merge `4e4bf45` | `pre-B0.2b-20260921-075754` / `post-B0.2b-20260921-111115` | Verified run `b2a5a24e`: 136 canonical_check + 12 per_field + 1 none |
| B0.3 — location only for positive findings | ✅ DONE | merge `a285b84` | `pre-B0.3-20260921-135411` / `post-B0.3-20260921-135450` | `_is_positive_location_finding` + Rule 1b в `_build_cell_value`. Универсальный whitelist `(ui_mode, review_status)`. Legacy `review_status=None` сохраняет cell_state-семантику. `unclear` сохранён как manual-review aid. Live-verified: CoC → `location_source="none"`, positive ячейки → `canonical_check`/`per_field`. Regression diff пустой (29 предсуществующих failures не связаны) |
| B0.4 — bbox_union в snapshot chunks + проброс в CheckResult | ✅ DONE | `85301d6` + `57bdce6` / merge `d7a3851` + `49fa9e9` | `pre-B0.4-20260921-144231` / `post-B0.4-20260921-145648`, `pre-B0.4b-20260921-153256` / `post-B0.4b-20260921-153523` | `_build_element_bbox_map` + `_compute_bbox_union` в `segment_chunk_builder_v2.py` → `meta["bbox_union"]` per chunk (page-matched union, multi-page fallback). B0.4b: проброс через `extraction_contexts` whitelist в executor. `CheckResult.bbox = {"union": [x0,top,x1,bottom], "page": N, "element_ids": [...]}`. Universal: any doc / check / ui_mode. Live-verified run `ec692954`: **34/34 filled** (0 null). CoC → `[85.15, 304.95, 572.45, 380.38]` (page 4), control → `[85.15, 278.5, 572.4, 315.98]` (page 1) |
| B0.5 — context_trace.score_breakdown | ✅ DONE | `73ce101` / merge `2632e21` | `pre-B0.5-20260921-160717` / `post-B0.5-20260921-160921` | Проброс top-level `score_breakdown` из retrieval chunk в `extraction_contexts` (executor L1185). `context_trace[i].score_breakdown` = `{bm25_raw, bm25_norm, dense_raw, dense_norm, metadata_raw, metadata_norm, weighted_sparse, weighted_dense, weighted_metadata, combined_score}`. Unit-тесты 4 PASSED. Live-verified run `ef76f962`: все 10 полей; `combined_score` == `score` (0.711 для CoC, 0.877 для control) |
| B0.6 — DD Grid LOCATION → viewer page mismatch (frontend) | ✅ DONE | `16c793f` / merge `a9093fa` | `pre-B0.6-20260921-170650` / `post-B0.6-20260921-170828` | `DocumentViewerModal::handleDocumentLoad` больше не сбрасывает на page 1 при `location.page > numPages` (race с `useEffect [location]` при первой загрузке PDF, когда `numPages=0`). Теперь: clamp к `numPages` только если `numPages > 0`; при валидном `targetPage ≤ numPages` не трогает `pageNumber`. Универсально для любого PDF и page. Verified в браузере: клик на p. 4 → modal на p. 4 |
| B0.6b — DDGridV1List: clauseUid должен быть canonical | ✅ DONE | `6465024` / merge `7c01e38` | `pre-B0.6b-20260921-171825` / `post-B0.6b-20260921-171912` | `DDGridV1List.tsx:796` — `clauseUid` теперь из `firstField.location_clause_uid` (canonical `"main_contract:7.2"`), а не из `location_clause_ref` (`"п. 7.2"`). Viewer находит chunk для overlay. Правка одной строки, tsc clean |
| B1.1 — Sanitize structural markers in location_clause_ref | ✅ DONE | `3f5d972` / merge `ec7db44` | `pre-B1.1-20260921-164938` / `post-B1.1-20260921-165202` | `_is_structural_marker` (regex `^__[a-z][a-z0-9_]*__$`) + sanitize в `_normalize_location_bundle`. `_derive_clause_ref_from_uid` расширен с узкой проверки `__preamble__` на общий предикат. Unit-тесты 20 PASSED |
| B1a — CheckAnchor contract | ✅ DONE | `bbc6c2f` / merge `003c9c9` | `pre-B1a-20260921-180232` / `post-B1a-20260921-181125` | Pydantic `CheckAnchor` + `CheckAnchorMethod` (StrEnum) + ORM `CheckResultAnchor` + Alembic миграция `b63a43153958`. Partial unique index `uq_cra_one_primary`. 4 nullable колонки на `check_results`: `primary_anchor_id/method/confidence` + `anchor_stale`. Тесты: 24 Pydantic + 6 ORM |
| B1b — Repository skeleton | ✅ DONE | `e0e4845` / merge `5fa00d1` | `pre-B1b-20260921-182220` / `post-B1b-20260921-182554` | `CheckResultAnchorRepository`: create_many / list_for_check_result / get_primary / set_primary / clear_primary / delete_for_check_result / replace_for_check_result. 11 unit-тестов (`pytestmark = pytest.mark.asyncio`). Не вызывается пока — persistence wiring в B4 |
| B1cd — Drop legacy location fields | ✅ DONE | `6a30459` + `d24e876` / merge `40f44e1` | `pre-B1cd-20260921-185215` / `post-B1cd-20260921-191411` | Backend B1c: удалены `has_location_fallback` + `location_fallback_reason` из `DDGridCellValueDTO` / `DDGridDrawerFieldDTO` + pipeline (`_normalize_location_bundle` 5→3-tuple, `_extract_location_bundle` → 4-tuple с source_hint). Frontend B1d: `classifyDDGridV1LocationAvailability({location_source})`, удалены `LOCATION_FALLBACK_I18N` + `localizeLocationFallbackReason` + `locationFallbackReasons` из 4 JSON. Fixed pre-existing bug: `drawer.ts::classify` вызывался без `location_source` |
| B1e — legal_unit chunk_id canonical | ✅ DONE | `7cfe5c1` / merge `a0c320f` | `pre-B1e-20260921-193140` / `post-B1e-20260921-193447` | Root cause: `legal_unit_retrieval.py:372` строил compound `f"{doc_id}:{unit_id}"` без kind-маркера. В живых данных за 60 дней: 4355/6622 (72%) `chunk_id` без kind. Fix: `build_legal_unit_chunk_id(doc_id, effective_uid)` → `<doc_id>:legal_unit:<scope>:<raw_uid>` в `chunk_ids.py`; замена в `legal_unit_retrieval.py` + `metadata["fragment_id"]` для executor fallback. 6 новых тестов в `TestCanonicalChunkIdGeneration`. Baseline подтверждён через `git stash`: 15 failed / 222 passed → 15 failed / 228 passed (+6 наших). No backfill |
| B2a — Citation normalization | ✅ DONE | `20decde` / merge `5a45a97` | `pre-B2a-20260922-034425` / `post-B2a-20260922-035102` | `src/engine/checks/citation_normalization.py`: `normalize_text`, `normalize_with_index_map`. Правила: все whitespace (space/tab/newline/NBSP/narrow NBSP/thin/hair) → один ASCII space; ё→е; кавычки `« » „ “ ”` → ASCII; тире `— – − ‐ ‑ ‒` → `-`. Index map инварианты: `len(norm) == len(idx_map)`, `norm[i] == _normalize_char(text[idx_map[i]])`. 39 unit-тестов |
| B2b — Citation resolver | ✅ DONE | `7fb0b9f` / merge `1b6d4bb` | `pre-B2b-20260922-035159` / `post-B2b-20260922-035803` | `src/engine/checks/citation_resolver.py`: `resolve_quote_in_source(quote, source_text, layout_elements, ...)` → `CheckAnchor`. Ступени: exact_span (1.0) → fuzzy_span (ratio ≥ 0.75) → clause_only (0.5) → page_only (0.3) → none (0.0). Span в координатах оригинала через B2a index map. Span → element_ids через накопленные offsets (воспроизводит `materialize_text_from_element_ids`, включая разделитель при page break; при mismatch — element_ids пусты, diagnostics флаг). Round-trip validation. `source_content_hash` — SHA-256 source_text. Не вызывается пока — wiring в B3. 21 unit-тест |
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

## Инциденты и уроки

### B1a-migration-import

Миграция `b63a43153958` падала с `NameError: name 'postgresql' is not defined`. Скелет от `alembic revision -m` содержит только `import sqlalchemy as sa`, а тело миграции использует `postgresql.UUID(...)`. Урок: при подаче тела Alembic-миграции всегда приводить **полный** блок импортов, включая `from sqlalchemy.dialects import postgresql`.

### B1a-downgrade-minus-one

`alembic downgrade -1` в верификационном скрипте откатил **чужую** миграцию `7ea844f630e0` (VARCHAR(20→50)), не нашу `b63a43153958`. Урок: использовать только явный target `alembic downgrade <explicit_rev>`. Правило 5.7.

### B1a-EOL

`src/db/models/result.py` на master хранился с CRLF-переносами (единственный файл в проекте). Первая же правка (добавление 4 колонок) дала whole-file diff (1200 строк). Урок: перед первой правкой существующего файла — `git ls-files --eol <path>`. При `i/crlf` — отдельным chore-коммитом нормализовать до LF **до** семантических правок. Правило 5.8.

### B1b-asyncio-marker

Тесты `test_check_result_anchor_repo.py` падали с `async def functions are not natively supported`. `pytest-asyncio` в STRICT-режиме требует явный маркер. Урок: перед первым тестом в новом модуле — проверить `asyncio_mode` в `pyproject.toml` и найти канонический пример теста в том же слое. Правило 5.2a.

### B1b-pre-tag-dirty

Дважды подряд pre-tag ставился, когда рабочее дерево содержало правки (B1a, B1b). Pre-tag корректен (указывает на `origin/master`), но правило git-workflow требует clean tree. Урок: правило 5.1a — pre-tag hygiene.

### B1cd-pre-existing-failures

После B1c/B1d `pytest tests/unit/services/ tests/unit/scripts/` показал 18 failures в `test_result_presentation_*`, `test_instruction_editor_service`, `test_enricher_per_unit_timeout`. Baseline через `git stash` → тот же набор падений на чистом master → `git stash pop` подтвердил: не наша регрессия. Урок: перед merge с failures — baseline-проверка обязательна.

### B1e-import-assumption

При патче `legal_unit_retrieval.py` я предположил наличие `from engine.content.chunk_ids import ...` в блоке импортов без проверки. Скрипт упал с `AssertionError: no engine.content import found`. Урок: перед подачей патча для вставки/замены — **прочитать фактические строки-маркеры** (`head -50`, `grep -n "^from \|^import "`) и указать точное место вставки. Правило 5.2b.

### B2a-merge-F-stdin

`git merge --no-ff <branch> -F- <<'EOF'` упал с `error: could not read file '-'`. `git merge` не читает сообщение из stdin — только `git commit` умеет `-F-`. Урок: для `git merge` всегда `-F <path>`, никогда `-F-`.

### B2a-post-tag-on-wrong-commit

При падении `git merge` post-tag был создан на предшествующем коммите (`da16183`), а не на merge-коммите. Ветка уже удалена — восстановление через `git reflog` + `git branch <name> <lost-hash>`. Урок: **post-tag создаётся только после `git log --oneline -1` показывает merge-коммит в HEAD**.

### B2a-manual-paste-multiline-commit

Многострочный `git commit -m "..."` через paste в интерактивном терминале склеивается и уходит в continuation prompt. Урок: всегда через `-F /tmp/msg.txt` (для commit), для merge — тоже `-F /tmp/msg.txt`. Правило 5.3a.

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

### Дополнительные правила (выведены из B1a/B1b/B1cd)

- **5.1a (pre-tag hygiene):** перед `git tag` рабочее дерево должно быть clean (`git status` пусто, включая untracked). Если untracked-файлы не должны попасть в коммит — `git stash -u` перед тегом. Pre-tag всегда ставится на `origin/master`, а не на локальный HEAD с правками.

- **5.2a (test-scaffolding):** перед первым тестом в новом модуле — проверить `asyncio_mode` в `pyproject.toml` и найти канонический пример теста в том же слое. При `asyncio_mode=STRICT` + `async def test_*` — обязательно `pytestmark = pytest.mark.asyncio` на уровне модуля (или `@pytest.mark.asyncio` на каждой функции).

- **5.2b (audit-before-patch):** перед подачей патча на вставку / замену в существующем файле — прочитать фактические строки-маркеры (`head -50`, `grep -n "^from \|^import "`, `sed -n 'X,Yp'`) и указать точное место вставки. Не полагаться на «вероятно есть импорт X» / «вероятно это в конце файла». Запрещено подавать патч, не видев фактических строк, к которым он применяется.

- **5.3a (git message hygiene):** любые многострочные сообщения — через `-F <path>` (для `commit` допустим `-F-`). Для **`git merge`** `-F-` не работает — только `-F <path>`. Post-tag создаётся **только после** `git log --oneline -1` подтверждает merge-коммит в HEAD. Если merge упал — стоп, восстановление (при удалённой ветке: `git reflog` → `git branch <name> <hash>` → повтор), и только потом tag.

- **5.7 (downgrade-тест):** при проверке миграций использовать только явный target `alembic downgrade <explicit_rev>`. `alembic downgrade -1` запрещён в верификационных скриптах — он непредсказуем при разветвлённом графе ревизий.

- **5.8 (EOL-проверка):** перед первой правкой существующего файла — `git ls-files --eol <path>`. Если `i/crlf` — сначала отдельным chore-коммитом нормализовать до LF, до семантических правок. Проверка: `grep -c $'\r' <path>` → 0.

### Техдолг (не в текущем треке)

- Введение `.gitattributes` с `* text=auto eol=lf` — отдельный PR после полного `git ls-files --eol` аудита репо.

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

---

## Обновление 2026-09-25: что закрыто после 21.09

Полный трек за 4 дня → см. `docs/HANDOVER_v7.3.md`. Кратко:

### Track B, продолжение (B5.x → B6.x → B7.x)

- B5.3 — risk-aware DD Grid (COC pilot). CellRiskBadge frontend.
- B6.1 — anchors fix (R13 fuzzy-window, R14 page, R15 location, R21 quote-exists).
- B6.2 — detection quality (R04, R10, R23, R24).
- B6.3 — follow-ups.
- B7.1 — body candidate wins over ToC при коллизии uid.
- B7.2 — ToC-zone structural fix (3 слоя).
- B7.3 — попытка фикса detect_toc_block (ROLLBACK, 72/335 docs lost).
- B7.4 — TOC State Machine (закрывает сломанный detect_toc_block).
- B7.5 — Spatial matcher geometric hard-gate.
- B7.6 — ToC-zone heading filter (== "post_toc").
- B7.9 — structural markers drop page (continuation of B1.1: scope-prefixed main_contract:__preamble__).
- B7.9.1 — drop structural-marker base_location из location_fallback (`_resolve_field_location_bundle`).
- B7.9.3 — canonical_check skips structural-marker anchors (`_build_cell_value`, блок Priority 4).

### Track B, пункты B3/B4/B5 из этого документа

Де-факто закрыты через B6.x + B0.x:
- B3 — Citation Extraction интегрирована в B6.x (executor + extraction).
- B4 — Persistence Layer: таблица check_result_anchors + ORM (B1a).
- B5 — API + Frontend: anchor в DTO + viewer overlay (B0.6, B5.3).

Строки с ⏳ TODO в таблицах выше — неактуальны.

### Отменено

- B7.7 — synthetic uid в appendix. Docling выдаёт чистые атомы.
- B7.8 — Docling uid synthesis. Docling корректен.
- DoD quality_completeness_warranty.page=6 — снят. Корректное поведение: LOCATION пустой в UI.

### Актуальные приоритеты

См. `docs/HANDOVER_v7.3.md` → Раздел 4 (backlog) и Раздел 5 (волны).
