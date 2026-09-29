# Handover + Plan v7.6 — Steloom

**Дата:** 2026-09-29 (обновлено после B7.9.2 — anchor sync fix)
**Master HEAD:** `4c6fbc2`
**Базис:** v7.5 + B7.9.2 fix
**Как использовать:** вставить целиком в первое сообщение нового диалога.

> **Отличие от v7.5.** Единственное изменение по сути — закрыт B7.9.2
> (см. Раздел 2, подсекцию «🆕 B7.9.2 — Anchor sync»). Раздел 4 (backlog)
> сокращён: секция B7.9.2 помечена закрытой. Остальное содержимое —
> как в v7.5.

---

## Changelog v7.5 → v7.6

| # | Что | Где |
|---|---|---|
| 1 | **B7.9.2 закрыт**: universal clause_ref parser + sync `cr.*` из primary anchor | Р. 2 |
| 2 | Новый модуль `core.anchors.clause_ref_parser` — numeric/latin/cyrillic/mixed/appendix маркеры, отделяет page refs (стр./page/p.) | Р. 2 |
| 3 | `_extract_numeric_core` делегирует в universal parser (`4260c16`) | Р. 2 |
| 4 | `_replace_anchors_for_check_result` синхронизирует `cr.page/clause_uid/element_id/bbox` из primary anchor (`2dd7086`) | Р. 2 |
| 5 | Runtime verify: run `17156da9-a771-4ea4-9a7f-8069a4183757` на NDA — **23/23 field_extraction ok, 0 mismatch** | Р. 2 |
| 6 | Baseline: `tests/unit/` — 37 pre-existing failed (те же, что до B7.9.2), 1701 passed | Р. 1 |
| 7 | Отложены: Fix B2 (`field_name` в `CheckAnchor`), Fix B3 (`display_priority` в selection) | Р. 4 |
| 8 | Гипотеза из v7.5 (`не merge'ить retrieval_provenance для field_extraction`) — **не подтвердилась** | Р. 3 |

---

## Changelog v7.4 → v7.5

| # | Что | Где |
|---|---|---|
| 1 | v3-промт для doc-type обновлён (`docs/TASK_CHECK_CALIBRATION_DOC_TYPE.md`) | Р. 12 |
| 2 | Bulk-калибровка 10 doc-type файлов — `f09c460` | Р. 2 |
| 3 | NDA: 15→21 check (+6 M&A/IC) — `2b0c0fb` | Р. 2 |
| 4 | Employment: 21→34 check (+13 M&A/IC) — `31b0efb` | Р. 2 |
| 5 | B0.4 доделка — `bbox_map` в layout fallback — `13a4de6` | Р. 2 |
| 6 | `scripts/cleanup_yaml_artifacts.py` v2 — `c894108` | Р. 12 |
| 7 | Merge `feat/v3-doc-type-calibration` → `1e12749`, запушено | Р. 1 |
| 8 | Verify на demo: 42/42 DOCUMENT_TYPE с `presence_signal` (run `dc100c68`) | Р. 2 |
| 9 | i18n demo bug закрыт (права файлов + umask 0077) | Р. 4 |
| 10 | Новые тикеты T1–T5 | Р. 4 |

---

## Changelog v7.3 → v7.4

| # | Что | Где |
|---|---|---|
| 1 | Stream A завершён: 44 global checks, 27 YAML-правок в 13 файлах | Р. 2, Р. 12 |
| 2 | Создан `scripts/audit_global_checks.py` | Р. 12 |
| 3 | Сформирован `CONSIDER_PACKAGE_v1.md` (19 пунктов) | Р. 12 |
| 4 | Волна 3: global checks DONE, осталось 7 doc_types | Р. 5 |
| 5 | Track A: A1 сделан частично; A2 ждёт юриста | Р. 2 |
| 6 | Uncommitted YAML-правки в 13 файлах global_checks | Р. 1, Р. 10 |
| 7 | Уточнён master HEAD: `12c45bb` | Р. 1 |

---

## Раздел 0. Ключевые принципы работы (читать первым)

### Принцип №1: «Аудит до 100%, потом продакшн-фикс»

**Перед любой правкой обязательно:**

1. **Аудит текущего кода** — прочитать функцию целиком, посмотреть все вызовы, `git log -L` на историю.
2. **Аудит данных** — увидеть сырой источник (PDF/DOCX XML), промежуточный артефакт (Docling output, layout.json), фактическое состояние в БД.
3. **Аудит гипотезы** — если гипотеза не подтверждается на данных, отменить её без сожаления.
4. **Только при 100% понимании root cause** — писать фикс.

**Правило отсечения:**
- Не уверен в точке правки — не писать.
- Не видел всех вызовов — не писать.
- Не проверил regression blast radius — не писать.

**За сессию 24–25.09 три гипотезы были отменены** после диагностики: B7.3 (rollback), B7.7 (synthetic uid), B7.8 (Docling synthesis). Каждая отмена сэкономила недели работы в неверном направлении.

### Принцип №2: «Фикс структурный, не костыль»

Правило формулируется через **класс явлений**, не через конкретный документ/uid/язык:
- ✅ «Structural marker + page без clause_ref — не anchor» — про класс `^scope?:__*__$`.
- ❌ «Если uid == `__preamble__`, то page = None» — подгонка под документ.

### Принцип №3: «Verify на реальном документе»

Каждый фикс проверяется на живом run:
1. Restart нужного worker.
2. Загрузить PDF как **новый документ** (layout собирается один раз на document_version).
3. SQL + UI verify.
4. Regression baseline (git stash → pytest → git stash pop).

### Принцип №4: «Git workflow строгий»

Pre-tag → ветка → правки → тесты → baseline → merge `--no-ff -F <path>` → post-tag → push → удаление ветки.
Post-tag только после `git log --oneline -1` подтверждает merge в HEAD.

### Принцип №5 (новый): «Скриптуемое — скриптуем»

Автоматизируемые проверки (форма, структура, дубли, placeholder'ы) — прогоняются скриптом. Семантические решения — за юристом. **Не путать.**

---

## Раздел 1. Текущее состояние master

```
master = 4c6fbc2   [origin/master]   (push after merge)
Working tree: clean

История (свежая):
4c6fbc2  Merge B7.9.2 — anchor sync fix
2dd7086  fix(db): B7.9.2 — sync cr.* location from primary anchor
4260c16  fix(extraction): B7.9.2 — _extract_numeric_core delegates to universal parser
a73bfa4  fix(anchors): support comma-separated marker lists in clause_ref parser
dd677b2  feat(anchors): universal clause_ref parser (B7.9.2)
372965e  docs(playbook): clarify prompt_template vs llm_prompt_extraction usage
59c98c7  fix(playbooks): NDA — v3-калибровка nda_parties_and_type_check + токены
1e12749  Merge feat/v3-doc-type-calibration: v3-промт + 13 M&A/IC checks + bulk-калибровка 10 doc-type + доделка B0.4

Теги:
pre-B7.9.2-fix-20260929-140210
post-B7.9.2-fix-20260929-160713
```

**Архивный тег:** `archive/infra-reaper-race-fixes-20260919` → `c9afa43`.
24 коммита infra/reaper/race-condition workstream (16–19.09) сохранены, ветка не активна.

**Все ключевые теги (последние 15):**
- `post-B7.9-honest-field-anchor-20260925-035940`
- `pre-B7.9-merge-20260925-035930`
- `pre-B7.9-honest-field-anchor-20260924-190114`
- `post-B7.5-spatial-matcher-20260924-155549`
- `pre-B7.5-merge-20260924-155511`
- `post-B7.6-toc-zone-filter-20260924-141421`
- `pre-B7.6-merge-20260924-141412`
- `post-B7.4-toc-state-machine-iter2-20260924-060233`
- `pre-B7.4-toc-state-machine-20260924-052716`
- `post-B7.4-toc-state-machine-20260924-050756`
- `pre-B7.4-toc-state-machine-20260924-043548`
- `post-B7.1-B7.2-toc-fixes-20260924-040313`

Полный список: `git tag -l --sort=-creatordate | head -30`.

**Baseline тестов:**
- `tests/services/structure/` — 845 passed, 10 skipped.
- `tests/services/document_layout/` — 10 passed (matcher).
- `tests/services/` — 1027 passed, 10 skipped, 2 pre-existing failed (`test_phase14_3b_embedding_vector_cache.py::*`, unrelated).
- `tests/unit/engine/` — 24 failed / 733 passed / 1 error (по v7.2, требует перепроверки).

## Раздел 2. Что закрыто (B0.x → B7.9)

### Track B — Anchor & Location

| Этап | Что | Коммит |
|---|---|---|
| B0.1 | sized-chunks `clause_uids`/`raw_uids` | `a1a3f0d` |
| B0.2 | `element_id` (layout UUID) + `chunk_id` (canonical) | `969ca8b` |
| B0.2b | `location_source` enum + clause_ref derive | `407684f` |
| B0.3 | location only for positive findings | `a285b84` |
| B0.4 | `bbox_union` в snapshot chunks + проброс в CheckResult | `d7a3851` |
| B0.5 | `context_trace.score_breakdown` | `73ce101` |
| B0.6 | DD Grid LOCATION → viewer page mismatch (frontend) | `a9093fa` |
| B0.6b | `DDGridV1List` clauseUid canonical | `7c01e38` |
| B1.1 | Sanitize structural markers (bare `__preamble__`) | `ec7db44` |
| B1a | `CheckAnchor` contract + ORM + миграция | `003c9c9` |
| B1b | Repository skeleton | `5fa00d1` |
| B1cd | Drop legacy location fields | `40f44e1` |
| B1e | legal_unit `chunk_id` canonical | `a0c320f` |
| B2a | Citation normalization | `5a45a97` |
| B2b | Citation resolver | `1b6d4bb` |
| B3 | Citation extraction (интегрировано в B6.x) | — |
| B4 | Persistence layer (таблица `check_result_anchors`) | — |
| B5 | API + Frontend (anchor в DTO, viewer overlay) | — |
| B5.3 | Risk-aware DD Grid (COC pilot) | `0fd4aa7` + `28a77c9` |
| B6.1 | Anchors fix: R13+R14+R15+R21 | `87900fc` |
| B6.2 | Detection quality: R04, R10, R23, R24 | `66e75a5` |
| B6.3 | Follow-ups | `b61183a` |
| B7.1 | Body candidate wins over ToC при коллизии uid | `21948c6` |
| B7.2 | ToC-zone structural fix (3 слоя) | `21948c6` |
| B7.4 | TOC State Machine (заменяет `detect_toc_block`) | `257092c` |
| B7.5 | Spatial matcher geometric hard-gate | `586b425` |
| B7.6 | ToC-zone heading filter (`== "post_toc"`) | `929a57c` |
| **B7.9** | Structural markers drop page (завершает B1.1) | `05a72ca` |
| **B7.9.1** | Drop structural-marker `base_location` из `location_fallback` | `754ac98` |
| **B7.9.3** | canonical_check skips structural-marker anchors | `12c45bb` |

### Track A — Detection Quality Audit

| Этап | v7.3 | v7.4 |
|---|---|---|
| A0 | presence_signal для field_extraction | ✅ DONE (21.09) |
| A1 | Программный аудит (SQL) | ✅ Частично сделан через `audit_global_checks.py` |
| A2 | Ручной аудит (юрист) | ⏳ ждёт `CONSIDER_PACKAGE_v1.md` |
| A3 | Аудит YAML | ⏳ ждёт юриста + product |
| A4 | Калибровка порогов | ⏳ после A2 |
| A5 | Улучшение промптов | ⏳ после A2+A3 |

**Track A всё ещё заблокирован на юридический аудит по A2/A3.** Но A1 разблокирован и частично выполнен для global checks.

### 🆕 Session 28.09 — v3 doc-type + M&A/IC checks

**Цель:** применить промт v3 к doc-type checks + добавить M&A/IC-специфичные checks для NDA и трудового договора.

**Что сделано:**

| Шаг | Результат | Коммит |
|---|---|---|
| v3-промт для doc-type | `docs/TASK_CHECK_CALIBRATION_DOC_TYPE.md` (v2 → v3) | `906aa1f` |
| Bulk-калибровка 10 doc-type файлов | +38427 / −4387 строк | `f09c460` |
| NDA: 15 → 21 check (+6 новых) | self-conf, severability, access-log, KT regime, negotiation-conf | `2b0c0fb` |
| Employment: 21 → 34 check (+13 новых) | IP, retention, equity, related-party, authority, whistleblowing, pension + 6 ТК-блок | `31b0efb` |
| B0.4 доделка | `bbox_map` в `_build_snapshot_via_layout_fallback` | `13a4de6` |
| Alimony: rename enum-полей | `adjustment_procedure_code`, `family_category_code` | `7f71c6a` |
| `scripts/cleanup_yaml_artifacts.py` (v2) | Line-based dedup retrieval.* + Layer 1 normalization | `c894108` |

**v3-промт — что изменилось от v2:**
- Запрещено добавление `<location_instructions>` (RF10).
- Финальная строка `<output_expectations>` про «отдельный контракт JSON».
- Layer 2 порядок: `<role> → <context> → <task> → <context_rules> → <edge_cases> → <output_expectations>`.
- `<edge_cases>` — строго 4 типовых сценария.
- `presence_signal` — строго после `compact_output`, до `llm_prompt_extraction`.
- `risk_weight` — дифференцированно (`high/medium/low/info`).

**Верификация на demo (run `dc100c68`, проект `test 14`):**
- 42/42 DOCUMENT_TYPE checks содержат `*_presence` в `structured_data` ✅
- `risk_weight` присутствует в `playbook_versions.compiled_checks` ✅
- UI показывает `riskWeight.high` ✅
- i18n на demo восстановлен (см. Раздел 4, T2) ✅

### 🆕 Stream A — Global Checks Cleanup (2026-09-25)

**Цель:** привести 44 global checks в `playbooks/global_checks/*` в соответствие с требованиями кода и промптов (B7.10 + Wave 3).

**Что сделано:**

| Шаг | Результат |
|---|---|
| Создан скрипт `scripts/audit_global_checks.py` (v1→v2→v3) | Трёхуровневый автоматический аудит |
| Прогон на 44 checks | STRUCT 44✅ / PSIG 44✅ / RW 44✅ / L2 44✅ / DEEP 13⚠️ |
| Правка №1: `<STATUS_FIELD>` → конкретное поле | 7 файлов |
| Правка №2: слияние дубля `<context_rules>` | 7 файлов |
| Правка №3: опечатка `налиличие → наличие` | 1 файл |
| Правка №4: удаление дублей в обязательных полях | 10 файлов |
| **Всего YAML-правок** | **27, в 13 уникальных файлах** |

**Статус:** ✅ Все YAML-правки применены в рабочем дереве. ⏳ Ждут git-commit + перекомпиляцию playbook в БД.

### Детали B7.5 (ключевой фикс)

**Проблема:** Orphan-маркеры из ToC-зоны матчились с атомами appendix-листинга с `y_delta = 65-155 pt`. Формула confidence компенсировала нулевой y-компонент за счёт x/column/marker.

**Фикс** (`src/services/document_layout/spatial_marker_recovery.py`):
- `SpatialMatcher._is_spatially_compatible` — hard-gate до scoring:
  ```python
  max_y_delta = max(2.0 * fingerprint.y_tolerance, fingerprint.median_line_height, marker.font_size)
  if y_delta > max_y_delta: return False
  ```
- `x_gap = atom.bbox[0] - marker.bbox[2]` — единая конвенция.
- Dummy-столбцы в cost matrix Hungarian — атом может остаться без пары.
- `_MIN_ACCEPT_CONFIDENCE = 0.5`.

**Verify:** `spatial_recovery = 0` в layout. 10 unit-тестов.

**Diagnostics:** `scripts/diagnostics/trace_uid_collision.py` — трассировка uid-коллизий.

### Детали B7.6

**Проблема:** `_filter_toc_zone_headings_when_body_headings_exist` фильтровал `in_toc` headings при наличии хотя бы одного heading вне ToC. Критерий `!= "in_toc"` цеплял `pre_toc` и unknown-zone — suppress'ил валидные ToC-fallback'и.

**Фикс:**
- `_pipeline/_core_builder.py` — `non_toc_present == "post_toc"` вместо `!= "in_toc"`.
- `_heading_builder/_core.py` — non-numeric structural uid принимается только при `decision == "accepted"`.

**Verify:** `clause_uid` сдвинулся с `__preamble__` на `main_contract:7.3`. 4 unit-теста.

### Детали B7.9 (последний фикс)

**Проблема:** `dd_grid_v1_builder._normalize_location_bundle` обнулял `clause_ref` при structural marker (`__preamble__`), но сохранял `page`. Frontend рендерит `location_page` **независимо** от `location_clause_ref` — пользователь видел «стр. 2» без указания пункта.

**Фикс** (`src/services/dd_grid_v1_builder.py`):
- `_is_structural_marker` распознаёт scope-prefixed форму:
  ```python
  _SCOPED_STRUCTURAL_MARKER_RE = re.compile(r"^[A-Za-z0-9_]+:__[a-z][a-z0-9_]*__$")
  ```
- `_normalize_location_bundle` при structural marker возвращает `(None, None, confidence)` — оба поля обнуляются.

**Verify на run `f5fd3359`** (13 checks):
- `quality_completeness_warranty.LOCATION = —` (пусто) ✅
- Остальные 12 checks сохранили корректные локации ✅

**Tests:** 18 unit в `tests/services/test_dd_grid_v1_builder_location.py`.

---

### 🆕 B7.9.2 — Anchor sync (2026-09-29)

**Проблема (была).** 12 из 22 `field_extraction` checks на NDA X5 показывали
MISMATCH между `cr.clause_uid` и `anchor.clause_uid`. UI читает `cr.clause_uid`
(см. `frontend/src/components/documents/ReviewCheckCard.tsx:31`,
`frontend/src/utils/viewerLocation.ts:28`,
`src/api/schemas/deal_review.py:1337-1339`) — пользователь видел не тот пункт.

**Причина (реальная).** Наложение **двух** независимых багов:

1. **`_extract_numeric_core`** (`src/engine/checks/extraction.py:213`) использовал
   regex `\d+(?:\.\d+)*` — только цифры. Для preamble-кейса
   `clause_ref = "пункт S, СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ, стр. 1"` regex
   возвращал `["1"]` (номер страницы!) вместо `["S"]`. Priority 1 в
   `_resolve_field_anchor` находил чанк с `raw_uid="1"` → `main_contract:1`.
   Правильный uid — `main_contract:S` (канонический контракт
   `toc_parser.parse_raw_heading`: ALL-CAPS body-heading без номера → uid `"S"`;
   см. `src/services/structure/toc_parser.py:490`, подтверждено в chunk store
   `chunks_fe2d4d99.json` и `legal_units_fe2d4d99.json` на S3/MinIO).

2. **`cr.page/clause_uid/element_id/bbox`** заполнялись из R15 top-1 retrieved
   chunk (via `_extract_detector_provenance` в
   `src/engine/checks/executor.py:160`), а primary anchor указывал на другой,
   более точный чанк (найденный через `resolve_quote_in_source` →
   `EXACT_SPAN`/`FUZZY_SPAN`). `_replace_anchors_for_check_result` устанавливал
   `primary_anchor_id`, но **не синхронизировал** `cr.*` из anchor. UI читает
   `cr.clause_uid` → mismatch.

**Гипотеза из v7.5 (не подтвердилась).** «Убрать `_merge_provenance` для
`is_field_extraction` в executor». Аудит показал: `_merge_provenance` работает
корректно, проблема не в нём.

**Fix (4 коммита в ветке `fix/B7.9.2-anchor-sync`).**

- `dd677b2` — новый модуль `src/core/anchors/clause_ref_parser.py`: парсит
  numeric / latin / cyrillic / mixed / appendix маркеры; отделяет page refs
  (`стр. N`, `page N`, `p. N`) — универсальный, без хардкода под NDA.
- `a73bfa4` — support `"п. 7.1.1, 7.1.2"` (comma/semicolon-separated markers
  после одного префикса).
- `4260c16` — `_extract_numeric_core` делегирует в universal parser
  (backward-compatible wrapper; method name сохранён).
- `2dd7086` — `_replace_anchors_for_check_result` (`src/db/repositories/result_repo.py`)
  синхронизирует `cr.page/clause_uid/element_id/bbox` из primary anchor для
  `field_extraction`. Guards: `EXACT_SPAN` всегда, `FUZZY_SPAN` conf ≥ 0.5
  (`_ANCHOR_SYNC_MIN_CONFIDENCE`); weak methods (`CLAUSE_ONLY` / `PAGE_ONLY` /
  `LAYOUT_ONLY` / `RETRIEVAL_LEGACY`) не трогают `cr.*`; sync срабатывает
  только если anchor реально несёт значение (не затирает null).

**Verify (runtime).**

- Run `17156da9-a771-4ea4-9a7f-8069a4183757` на NDA
  (документ `38f03f53-abe8-4034-8651-a09d53285da2`, doc_type `contract_7.4_nda`).
- SQL: `SELECT COUNT(*), COUNT(*) FILTER (WHERE cr.clause_uid = cra.clause_uid), COUNT(*) FILTER (WHERE cr.clause_uid != cra.clause_uid) FROM check_results cr JOIN check_result_anchors cra ON cra.id = cr.primary_anchor_id WHERE cr.run_id = '17156da9-...' AND cr.ui_mode = 'field_extraction'`
  → **23 / 23 / 0 mismatch**.
- Preamble: `nda_parties_and_type_check` → `cr.clause_uid = anchor.clause_uid = main_contract:S`, page=1, method=`exact_span`.
- Baseline: `tests/unit/` — **37 pre-existing failed** (идентично состоянию до B7.9.2, проверено через `git checkout pre-B7.9.2-fix-20260929-140210` + `diff`), **1701 passed** (+23 новых).

**Отложено.** Fix B2 (`field_name` в `CheckAnchor` + миграция) и Fix B3
(`select_primary_anchor_for_check` с `display_priority`) — **не блокируют
B7.9.2**, не реализованы. Если понадобится семантический выбор primary anchor
по приоритету полей (для UI показа первого поля карточки) — отдельная задача.

## Раздел 3. Отменённые гипотезы (не делать снова)

| Гипотеза | Причина отмены |
|---|---|
| **B7.3** — `detect_toc_block` end_index = `last_entry_i + 1` | 16/18 passed, но 72/335 документов потеряли ToC. Откат. Заменён на B7.4 (State Machine). |
| **B7.7** — synthetic uid в appendix | Docling выдаёт чистые атомы (`marker=None` для `ПРИЛОЖЕНИЯ`, `Приложение № N`). |
| **B7.8** — Docling uid synthesis | Docling корректен. |
| **DoD `quality_completeness_warranty.page=6`** | Снят. Корректное поведение для документа без клаузы о качестве: `page=2, clause_uid=__preamble__` в БД, **LOCATION пустой в UI**. |

**Методический вывод:** каждая отменённая гипотеза была «логически правдоподобной». Отменяли их после аудита данных: PyMuPDF dump PDF, Docling output dump, `git log -L` на функцию.

### 🆕 Новое в v7.4 (Stream A)

| # | Гипотеза | Статус |
|---|---|---|
| 1 | «У всех 44 checks есть `<STATUS_FIELD>`» | Отменена — только 7 файлов |
| 2 | «list_dups в `retrieval.*` — by design» | Отменена — копипаст, удалено в 10 файлах |
| 3 | «v3-скрипт найдёт все placeholder'ы» | Уточнена — не ловит семантические дубли `<context_rules>` с разной лексикой |

## Раздел 4. Открытый backlog (что осталось)

### Открытые задачи Session 28.09 (T1–T5)

| # | Задача | Тип | Приоритет |
|---|---|---|---|
| **T1** | Global checks: 4 записи `origin=GLOBAL_PLAYBOOK` без `presence_signal` в structured_data, при 45/45 published в `global_instruction_versions` | code/checks (out of scope v3) | MEDIUM |
| **T2** | ✅ **CLOSED 28.09.** i18n demo bug: файлы `frontend/*/locales/**` имели права 600 (umask 0077 в live SSH-сессии). Caddy (другой UID) получал 403 → i18next raw keys. Fix: `chmod 644` + `umask 0022` в `~/.bashrc` | infra | — |
| **T3** | Verify NDA/Employment на demo (нужны документы соотв. типов) | runtime | MEDIUM |
| **T4** | 30 оставшихся doc-type файлов (v3-калибровка) | code | **HIGH** |
| **T5** | Fallback processing на `vehicle_supply_check` (LLM не отдал валидный JSON) | checks | LOW |

**Дополнительно к T2 (hardening, не блокер):**
- Добавить `chmod -R a+rX dist` в `package.json` → `build` (post-build защита).
- Проверить PAM/login.defs — не найдено источника 0077 (разовый, не системный).

**Stream A — 5 follow-up задач (закрыты/перенесены):**
- 4.1 ✅ Commit Stream A (в v7.4).
- 4.2 ✅ Перекомпиляция playbook.
- 4.3 ⏳ Ревью юриста `CONSIDER_PACKAGE_v1.md` — 19 пунктов.
- 4.4 🔀 Заменена на T4 (30 файлов, не 7).
- 4.5 ⏳ Финальный `audit_v4`.

### Точечные наблюдения Stream A (вне R-* backlog)

| # | Наблюдение | Где | Приоритет |
|---|---|---|---|
| S1 | Агрегаторы не покрывают комбинацию (present + unclear) | 2 файла | LOW |
| S2 | Нетипичные enum'ы (`pre_claim_procedure_status` и др.) | 2 файла | LOW |
| S3 | Семантика `present` при прямом исключении (RF3) | 2+ файла | LOW |
| S4 | Keyword overlaps `high ∩ low` — by design | 44 | IGNORE |

### ✅ B7.9.2 — CLOSED in v7.6 (anchor sync)

Перенесено в Раздел 2 (подсекция «🆕 B7.9.2 — Anchor sync»).
Корневая причина оказалась не в `_merge_provenance` (гипотеза v7.5 опровергнута),
а в двух других багах: regex `_extract_numeric_core` + отсутствие синхронизации
`cr.*` из primary anchor. Verify: run `17156da9`, 23/23 ok, 0 mismatch.

### B7.4.5 — appendix-tail в ToC

**Проблема.** 25 из 335 документов (7.5%) теряют 3–4 завершающих ToC-строки appendix-family без uid (`ПРИЛОЖЕНИЯ`, `APPENDIX No. N`). Осознанный trade-off B7.4.

**Решение.** Расширить `_is_likely_toc_entry_line` или добавить `_is_appendix_family_toc_line` в `toc_parser.py`. Условие: appendix-строки считаются entry только в контексте ToC-кластера (после entry-строк, до первого body-heading).

**Приоритет.** Опционально.

### Backlog R-* (12 открытых)

**Средние (9):**
- R02 — `presence_signal` семантически двусмыслен
- R06 — `_PRESENCE_NOT_FOUND_SOURCES` узкий
- R07 — `negative_keywords` substring
- R08 — `_MIN_EVIDENCE_LENGTH=20`
- R09 — `_EXTRACTION_TOKEN_FACTOR=3.8` hardcoded
- R11 — `context_trace max_items=5`
- R17 — rules-based не даёт location
- R18 — `_validate_allowed_values` mismatch
- R22 — `_select_best_chunk` rules = top-1

**Низкие (4):**
- R01, R19, R20, R25

**Всего 12 открытых.**

---

## Раздел 5. Плановые волны

### 🔴 Волна 3: Layer 2 bulk-roll — **global DONE, doc_types В РАБОТЕ**

**Было (v7.3):** 44 файла P3b + 7 document_types.

**Стало (v7.5):**
- ✅ **44 global checks** — обработаны в Stream A.
- ✅ **12 из 42 `document_types/*.yaml`** — обработаны в Session 28.09:
  - 10 bulk (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.11, 2.1, 3.3, 4.2);
  - NDA (`contract_7.4`, +6 M&A/IC checks);
  - Employment (`contract_9.1`, +13 M&A/IC checks).
- ⏳ **30 файлов остаются** — T4 в backlog.

**Файлы для T4 (28 из 42, остались):**

- **Group 1 (ownership)** — 4 файла: `1.8_donation`, `1.9_annuity`, `1.10_assignment`, `1.12_accord`.
- **Group 2 (use)** — 3 файла: `2.2_rental`, `2.3_vehicle_lease`, `2.4_leasing`.
- **Group 3 (works)** — 2 файла: `3.1_works_contract`, `3.4_design_survey`.
- **Group 4 (services)** — 4 файла: `4.1_services`, `4.3_freight_forwarding`, `4.4_storage`, `4.5_insurance`.
- **Group 5 (financial)** — 5 файлов: `5.1_loan`, `5.2_credit_agreement`, `5.3_factoring`, `5.4_bank_deposit_account`, `5.5_guaranty_and_pledge`.
- **Group 6 (intermediary)** — 3 файла: `6.1_mandate`, `6.2_commission`, `6.3_agency`.
- **Group 7 (ip)** — 3 файла: `7.1_ip_assignment`, `7.2_license`, `7.3_franchise`.
- **Group 8 (partnership)** — 1 файл: `8.1_simple_partnership`.
- **Group 9 (special)** — 3 файла: `9.2_collective_agreement`, `9.3_prenuptial_agreement`, `9.5_founders_agreement`.

**Опционально (`9.4_alimony_agreement`)** — был частично обработан (`*_code` rename, `7f71c6a`), но без полного v3-промта. Решить отдельно: дорабатывать или оставить.

**Итого:** 28 файлов + 1 опциональный = 28–29.

**Уже обработаны (13 + 1):**
- Полностью v3: `1.1`, `1.2`, `1.3`, `1.4`, `1.5`, `1.6`, `1.7`, `1.11`, `2.1`, `3.3`, `4.2`, `7.4`, `9.1`.
- Частично: `9.4`.

**Registry** (`playbooks/document_types/registry.yaml`) — служебный, не в scope.

**Шаблон v3** (актуальный — `docs/TASK_CHECK_CALIBRATION_DOC_TYPE.md`):
- `<role> → <context> → <task (с п.0)> → <context_rules> → <edge_cases (4)> → <output_expectations>`;
- `presence_signal` — после `compact_output`, до `llm_prompt_extraction`;
- presence-field первым в `fields` (`risk_weight: info`);
- `risk_weight` — дифференцированно (`high`/`medium`/`low`/`info`);
- `<edge_cases>` — 4 сценария (полное отсутствие / неполное / противоречие / специфика);
- финальная строка `<output_expectations>` — «Технический формат JSON (value / confidence / location) задан отдельным контрактом…»;
- **НЕТ** `<location_instructions>` (запрещено RF10).

**Что делаем:** по двухшаговому паттерну v3 (обзор файла → 5 checks) расширить оставшиеся 28 файлов.

### 🔵 Волна 4: B3.6 — layout_element_ids (3–5 дней)

**Цель.** Проброс `layout_elements` через pipeline для точного `element_ids` в `CheckAnchor`.

**Файлы:**
- `src/engine/checks/executor.py` — проброс `layout_elements` в `extraction_contexts`.
- `src/services/structure/chunk_canonicalization.py` — metadata.
- `src/engine/checks/extraction.py::_resolve_field_anchor` — получает `layout_elements`.
- `src/engine/checks/citation_resolver.py` — `_compute_element_offsets` + preamble fix.

### ⚪ Волна 5: B4b + Layer 2.2 (2–3 дня)

1. **B4b** — `anchor_stale` (1–2 дня). Инвалидация anchor'ов при refresh контента.
2. **Layer 2.2** — 7 `document_types/*.yaml` (1 день). **Единственный оставшийся пункт «Волны 3».**

### Backlog (после стабилизации)

R02, R06, R07, R08, R09, R11, R17, R18, R19, R20, R22, R25.

---

## Раздел 6. Окружение

### Управление воркерами (tmux)

**Session:** `steloom-dev`, 9 окон:
```
0:backend     — uvicorn --reload (auto-reload)
1:frontend    — Vite HMR (auto-reload)
2:w-default   — worker-default (build_primary_language_source, extract, structure)
3:w-enrich    — worker-heavy-enrichment
4:w-segclass  — worker-heavy-segment-classification
5:w-checks    — worker-heavy-checks (checks, detectors, playbook)
6:w-system    — worker-system (DB repos, mas_queue)
7:beat        — celery beat
8:shell       — bash
```

**Restart worker-default:**
```bash
tmux respawn-window -k -t steloom-dev:w-default \
  'bash /home/steloom/dev-run/run-with-log.sh worker-default /home/steloom/dev-run/worker-default.sh'
sleep 10
tail -20 /home/steloom/dev-logs/worker-default.log
grep -E "START worker-default|ready\." /home/steloom/dev-logs/worker-default.log | tail -3
```

**Restart worker-checks:**
```bash
tmux send-keys -t steloom-dev:w-checks C-c
sleep 10
tmux send-keys -t steloom-dev:w-checks \
  "/home/steloom/dev-run/run-with-log.sh worker-checks /home/steloom/dev-run/worker-checks.sh" Enter
sleep 20
tail -30 /home/steloom/dev-logs/worker-checks.log
```

**Логи:** `/home/steloom/dev-logs/<name>.log`
**Скрипты:** `/home/steloom/dev-run/*.sh` (`start-all-tmux.sh`, `restart-all-tmux.sh`, `health-all-tmux.sh`, `attach-tmux.sh`)

### Worker Restart map (код → worker)

| Изменённый код | Worker |
|---|---|
| `src/api/**` | backend (uvicorn, авто) |
| `src/engine/checks/**`, `detectors/**`, `playbook/**`, `retrieval/**` | w-checks |
| `src/db/repositories/**` | backend + w-checks |
| `src/services/**`, `src/workers/**` | w-default |
| `src/engine/content/**` | w-enrich + w-checks |
| `frontend/**` | frontend (Vite HMR) |
| `playbooks/**` | + перекомпиляция playbook в БД |

### Окружение Python

```bash
cd /srv/steloom-dev
source .venv/bin/activate
export PYTHONPATH=src:.
which python    # /srv/steloom-dev/.venv/bin/python
python --version  # 3.12.3
```

### БД и артефакты

**PostgreSQL:** `sudo docker exec -i mas_dd_postgres psql -U mas -d mas_dd -c "..."`
**MinIO:** `mas_dd_minio`, bucket `steloom-dev-artifacts`

**Скачивание артефактов:**
```python
from storage.artifact_store import ArtifactStore
store = ArtifactStore()
data = store.get_json(ref)  # или get_file(ref)
```

**Ключевые таблицы:**
- `check_results` — результат чека, `page`, `clause_uid`, `structured_data`, `display_text`.
- `check_result_anchors` — anchors (B1a ORM).
- `document_versions` — `layout_primary_ref`, `original_ref`, `converted_pdf_ref`.
- `runs` — `id`, `deal_id`, `status`.

### Playbook в БД

YAML правки **не подхватываются без перекомпиляции в БД**. Механизм через UI/скрипт.

## Раздел 7. Правила git workflow (16 шагов)

1. `git checkout master && git status --short` — clean.
2. `git fetch origin && git pull origin master`.
3. Pre-tag `pre-<stage>-YYYYMMDD-HHMMSS` на `origin/master`.
4. Ветка `<type>/<stage>-...` от master.
5. Правки строго по diff'у.
6. Синтаксис: `ast.parse` + `npx tsc --noEmit`.
7. EOL: `git ls-files --eol`.
8. `git diff` — review.
9. Commit через `-F <path>` (не `-m`).
10. Push ветки.
11. Тесты: dedicated + regression.
12. Baseline-verify: `git stash -u` → pytest → `git stash pop`.
13. Merge `--no-ff -F <path>`.
14. `git log --oneline -1` — merge в HEAD?
15. Post-tag **только после** подтверждения merge.
16. Удаление ветки локально + origin.

### Подводные камни

- Pre-tag на clean tree (включая untracked).
- `asyncio_mode=STRICT` → `pytestmark = pytest.mark.asyncio`.
- Не оставлять non-empty `git status` перед merge.
- Audit-before-patch: `head -50`, `grep -n "^from"`, `sed -n 'X,Yp'`.
- При добавлении поля в DTO — правь все 3 слоя (internal dataclass → Pydantic → TS → mapping).
- React hooks — до early return.
- `python -c` с многострочником — через heredoc.
- `export PYTHONPATH=src:.` перед импортами.
- Многострочный `git commit` через paste склеивается — через `-F <path>`.
- Для `git merge` `-F-` не работает, только `-F <path>`.

---

## Раздел 8. Тестовые deals/runs

| Deal / Doc | Run | Notes |
|---|---|---|
| `5a193caa-4573-4d01-a1f5-cf23169de50d` | `f5fd3359-7fd1-4847-b7bd-bc48ee5b1ce7` | **Verify B7.9**: 13 checks pass, `quality_completeness_warranty.LOCATION = —` |
| doc `748bac1c-7548-4cd2-8652-a9f0c9fd2b31` | — | DOCX источник для verify B7.5, B7.6, B7.9 |
| `21679b18-9dd6-4a65-8c73-455caa534b63` | `308026a8-7afd-4793-aa46-8272ae56a30f` | Baseline B6.3 (4 анкора CoC) |
| `fd5fab6a-128b-437c-b669-4834fcfb9a38` | `2d2d9177-...` | Verify B7.6 |

**Demo runs (steloom_demo, БД `steloom_demo`):**

| Deal / Doc | Run | Notes |
|---|---|---|
| `test 14` (DOGOVOR.docx + Simonova SPA) | `dc100c68-ffde-46ae-bdd8-9ba9b2bd3180` | 59 checks: 42 doc-type + 4 global. Verify v3: 42/42 с `presence_signal`. Verify i18n fix. |

**Bundle/document для проверки ToC:**
- `document_id = d37201cc-c650-472d-ae88-3e9a9ae0743d`
- `bundle_id = 06aac1e1-297e-4e45-b842-8bdacabde940`
- `document_version_id = 780bf54d-8267-4dee-8501-a819393d3888`

### Важное про layout

**Layout собирается один раз на document_version.** `extract_document` — bypass, читает `document_run_language_resolution.layout_primary_ref`. Повторный run не пересобирает layout.

**Для verify изменений в `src/services/document_layout/**` — нужен новый upload PDF/DOCX.**

---

## Раздел 9. Ключевые уроки сессии 24–25.09

### Диагностика

1. **«Не мерджить до подтверждённого root cause»** — трижды гипотеза не подтвердилась (B7.3, B7.7, B7.8).
2. **Аудит данных обязателен:** PyMuPDF dump PDF, Docling output dump, `git log -L` на функцию, все вызовы `_is_*`.
3. **Смотреть сырой источник:** PDF/DOCX XML, а не только layout.
4. **Различать симптомы и root cause:** `page=2` был симптомом, источник — R15 + `_normalize_location_bundle`.
5. **Не спешить с фиксом:** B7.5 оказался реальным багом (spatial matcher), но не был причиной `page=2`.

### Архитектурные факты

1. **Layout один раз на document_version** — пересборка только через новый upload.
2. **Retrieval для field_extraction возвращает top-1 chunk.** R15 (`executor.py:1209–1233`) заполняет `detection["location"]` из `retrieved_chunks[0]`.
3. **DD Grid UI рендерит `location_page` независимо от `location_clause_ref`** — обнуление одного без другого оставляет misleading signal.
4. **`__preamble__` — structural marker, не clause.** `_derive_clause_ref_from_uid` уже это знает, `_normalize_location_bundle` теперь тоже.

### 🆕 Уроки Stream A (v7.4)

1. **Форма ≠ содержание.** Скрипт проверяет `presence_signal.field`, `risk_weight`, `<location_instructions>` — но не проверяет семантику агрегатора, консистентность `description` ↔ `<role>` или осмысленность `severity_if_fail`. Это за юристом.
2. **Placeholder'ы — это класс, а не единичный баг.** `<STATUS_FIELD>` нашёлся сразу в 7 файлах.
3. **Автодетектор дублей ловит не всё.** `<context_rules>` дубли в `payment_terms_and_structures` и `financial_covenants` имеют разные формулировки — ручной ревью обязателен.
4. **V1 → V2 → V3 скрипта** — эволюция по мере обнаружения новых классов багов.
5. **Все 27 правок — однотипны.** Позволило выдавать полные YAML-версии для копипасты.
6. **«As designed» — это тоже решение.** RF8 — не баг, если осознанно. Пакет `[CONSIDER]` для юриста важен так же, как сами правки.

### 🆕 Уроки Session 28.09

1. **Скоуп изоляции соблюдён.** v3-правки касались только `document_types/*`. Global checks (`global_checks/*`, `global_instruction_versions`) — зона Stream A, не пересекались.
2. **Runtime-верификация ≠ компиляция.** Просто «перекомпилировал playbook» недостаточно — надо проверить `structured_data` в `check_results` через SQL.
3. **Права файлов имеют значение.** `umask 0077` в одной SSH-сессии → `600` на локалях → Caddy 403 → i18n raw keys. Урок: i18n-bug с полным отсутствием namespace всегда начинается с проверки `curl -I` на URL локали.
4. **Differential diagnosis для i18n.** Скрины показывали raw keys **всех** namespace. Это означало «файл локали не загрузился целиком», а не «часть ключей отсутствует». Классический признак 403.
5. **`playbook_versions` ≠ `playbooks`.** В БД две системы: UI-конструктор (playbooks / playbook_versions) и YAML-based instruction_versions. Проверять надо оба.
6. **6 new M&A/IC-checks + 13 Employment — реализованы по единому шаблону.** Позволило выдавать полные YAML-версии без ошибок.

### Что не трогать

1. Retrieval engine — кроме B3.6 точечно.
2. Модель чанкинга — стабильна.
3. Sentence-level anchors — не вводим.
4. Backfill старых записей — не делаем.
5. Классификация, тенанты, RBAC.
6. Frontend viewer с нуля — только расширения.
7. Веса retrieval (0.3/0.6/0.1) — работают.
8. `content/citation_resolver.py` — не удаляем.
9. `_salvage_partial_json` — не переписываем.
10. B7.1 + B7.2 — оставляем как есть.

---

## Раздел 10. Команды старта нового диалога

```bash
cd /srv/steloom-dev
source .venv/bin/activate
export PYTHONPATH=src:.

git log --oneline -10
git branch -vv
git status --short
git tag -l --sort=-creatordate | head -15

# Stream A state
git status --short playbooks/global_checks/
git diff --stat playbooks/global_checks/
ls scripts/audit_global_checks.py 2>/dev/null && echo "audit script present"

# Re-run audit
python scripts/audit_global_checks.py --verbose \
  --json /tmp/audit_v4.json --csv /tmp/audit_v4.csv

# Worker status
tmux list-windows -t steloom-dev -F '#I:#W'
tail -5 /home/steloom/dev-logs/worker-default.log

# БД
sudo docker exec -i mas_dd_postgres psql -U mas -d mas_dd -c "
SELECT id, status, created_at FROM runs ORDER BY created_at DESC LIMIT 5;
"
```

**Первая задача нового диалога — выбор из:**

1. **T4** — продолжить v3 для следующих doc-type файлов (30 из 42 остались) — HIGH.
2. **T3** — загрузить NDA/Employment на demo, проверить новые checks (5 + 13) — MEDIUM.
3. **T1** — global checks presence (4 записи `GLOBAL_PLAYBOOK` без presence, out of scope v3) — MEDIUM.
4. **T5** — fallback processing на `vehicle_supply_check` — LOW.
5. **Ревью юриста `CONSIDER_PACKAGE_v1.md`** — если доступен — MEDIUM.
6. **Волна 4: B3.6 (layout_element_ids)** — архитектурная, 3–5 дней.

**Рекомендация:** начать с **T4** — основная задача (Layer 2 bulk-roll продолжается). Или **T3**, если есть подходящие документы для runtime-проверки новых checks.

---

## Раздел 11. История коммитов (последние 15)

```
12c45bb (tag: post-B7.9.3-canonical-check-marker-...) Merge branch 'fix/B7.9.3-canonical-check-marker'
16ad327 fix(dd-grid): B7.9.3 — canonical_check skips structural-marker anchors
754ac98 (tag: post-B7.9.1-honest-location-fallback-...) Merge branch 'fix/B7.9.1-honest-location-fallback'
abdce3b fix(extraction): B7.9.1 — drop structural-marker base_location from fallback
c2ad700 (tag: post-docs-v7.3-...) docs(plan): warn stale + changelog 21→25.09, link handover v7.3
6e12b80 docs(handover): v7.3 — B7.4/B7.5/B7.6/B7.9 закрыты, аудит репо
05a72ca (tag: post-B7.9-honest-field-anchor-...) Merge branch 'fix/B7.9-honest-field-anchor'
93fac4c fix(dd-grid): B7.9 — structural markers drop page, not just clause_ref
586b425 (tag: post-B7.5-spatial-matcher-...) Merge branch 'feat/B7.5-toc-body-uid-collision'
bce05c8 chore(B7.5): add spatial matcher diagnostics scripts
f5941e9 fix(B7.5): reject geometrically invalid spatial marker matches
929a57c (tag: post-B7.6-toc-zone-filter-...) Merge branch 'feat/B7.6-toc-zone-heading-filter'
d748219 fix(structure): B7.6 — ToC-zone heading filter respects post_toc confirmation
257092c (tag: post-B7.4-toc-state-machine-iter2-...) Merge branch 'feat/B7.4-toc-state-machine' (iteration 2)
3489dc8 feat(structure): B7.4 — TOC State Machine + extended entry criteria
```

---

---

## 🆕 Раздел 12. Артефакты Stream A

### Скрипт `scripts/audit_global_checks.py`

Автоматический аудит `playbooks/global_checks/*` — read-only.

**Проверяет:** STRUCT / PSIG / RW / L2 / RF (RF4, RF7, RF8, RF9, RF10) / DEEP (placeholder'ы, дубли служебных списков, дубли bullets, порядок тегов, keyword overlaps, опечатки).

**Запуск:**

    python scripts/audit_global_checks.py                      # сводка
    python scripts/audit_global_checks.py --verbose            # детали
    python scripts/audit_global_checks.py --only liability/    # фильтр
    python scripts/audit_global_checks.py --json out.json --csv out.csv

**Exit code:** 1 если есть `fail`, иначе 0.

**Развитие:** v3 — текущая. При новых классах багов — добавлять в блок DEEP.

---

### 13 файлов, изменённых в Stream A

**Группа 1 — STATUS_FIELD + дубль context_rules:**

    cyber/cybersecurity_policies_and_incidents.yaml
    cyber/outsourced_it_and_security_risk.yaml
    disputes/governing_law_and_forum.yaml
    disputes/limitation_periods_and_pre_claim_procedures.yaml
    finance/financial_covenants.yaml
    finance/payment_terms_and_structures.yaml
    finance/security_and_encumbrances_general.yaml
    sanctions/sanctions_clauses.yaml

**Группа 2 — удаление list_dups:**

    hr/hr_key_management_and_change_of_control.yaml
    ip_it/it_systems_access_and_data_export.yaml
    liability/liability_and_indemnity_scope.yaml
    liability/liability_caps_and_baskets.yaml
    liability/liability_exclusions.yaml
    rw/mac_mae.yaml
    sanctions/aml_kyc.yaml
    sanctions/export_control.yaml
    term/force_majeure.yaml
    term/term_and_renewal.yaml

**Итого:** 13 файлов (8 + 10 с пересечениями — уникально 13). 27 правок.

**Проверка одной командой:**

    cd /srv/steloom-dev
    for f in $(git diff --name-only playbooks/global_checks/); do
      python -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK  $f" || echo "FAIL $f"
    done

---

### CONSIDER_PACKAGE_v1.md — пакет для юриста

**Где:** `docs/CONSIDER_PACKAGE_v1.md`.

**Содержит:**
- **Категория 1 — RF8** (10 файлов): `severity_if_fail` ≠ `severity`. Требуется CONFIRM (as designed) / REJECT / CORRECT.
- **Категория 2 — RF9** (1 файл): `description` ↔ `<role>`.
- **Категория 3 — enum-critical** (8 файлов): валидность значения `critical`.
- **Дополнительно A–D:** агрегаторы, нетипичные enum'ы, семантика `present`, keyword overlaps.

**Всего пунктов ревью:** 19. **Уникальных файлов:** 13.

**После ревью:**
- Все CONFIRM — фиксируются как `as designed`.
- Все REJECT / CORRECT — формируется отдельный mini-round правок.

---

### Прогресс-трекер Stream A

| Категория | Всего | Готово |
|---|---:|---:|
| STRUCT, presence_signal, risk_weight, Layer 2, RF | 44 | 44 ✅ |
| YAML: STATUS_FIELD | 7 | 7 ✅ |
| YAML: дубль context_rules | 7 | 7 ✅ |
| YAML: опечатка | 1 | 1 ✅ |
| YAML: list_dups | 10 | 10 ✅ |
| CONSIDER: RF8 + RF9 + enum-critical | 19 | 0 (ждёт юриста) |

---

## 🆕 Раздел 13. Артефакты Session 28.09

### Коммиты (master, 1e12749)

| Коммит | Что |
|---|---|
| `906aa1f` | docs(plan): update doc-type calibration prompt to v3 |
| `13a4de6` | fix(content): pass bbox_map to layout fallback snapshot |
| `c894108` | feat(scripts): add cleanup_yaml_artifacts for retrieval dedup |
| `7f71c6a` | fix(playbooks): rename enum fields to *_code in alimony agreement |
| `2b0c0fb` | feat(playbooks): apply v3 calibration + add new checks for NDA |
| `31b0efb` | feat(playbooks): apply v3 calibration + 13 M&A/IC checks for employment |
| `f09c460` | feat(playbooks): apply v3 calibration to 10 doc-type contracts |
| `1e12749` | Merge feat/v3-doc-type-calibration |

### Изменённые файлы (16)

- `docs/TASK_CHECK_CALIBRATION_DOC_TYPE.md` — v2 → v3.
- `src/engine/content/segment_chunk_builder_v2.py` — B0.4 доделка.
- `scripts/cleanup_yaml_artifacts.py` — новый (v2, line-based).
- `playbooks/document_types/group_9_special/contract_9.4_alimony_agreement.yaml` — enum rename.
- `playbooks/document_types/group_7_ip/contract_7.4_nda.yaml` — v3 + 6 checks.
- `playbooks/document_types/group_9_special/contract_9.1_employment.yaml` — v3 + 13 checks.
- 10 doc-type файлов: `contract_1.11`, `1.2`, `1.3`, `1.4`, `1.5`, `1.6`, `1.7`, `2.1`, `3.3`, `4.2`.

### v3-промт — где

`docs/TASK_CHECK_CALIBRATION_DOC_TYPE.md` — обновлён, содержит Changelog v3 в конце.

### Новые checks — где

**NDA (`contract_7.4_nda.yaml`, +6):**
- `nda_self_confidentiality_check`
- `severability_check`
- `access_logging_check`
- `kt_regime_compliance_check`
- `negotiation_confidentiality_check`

**Employment (`contract_9.1_employment.yaml`, +13):**
- `ip_assignment_check`, `key_employee_retention_check`, `equity_compensation_check`
- `related_party_check`, `authority_limits_check`, `whistleblowing_and_anti_fraud_check`, `pension_program_check`
- `combined_work_check`, `transfer_check`, `suspension_check`
- `segregation_of_duties_check`, `second_job_approval_check`, `pending_disputes_history_check`

### Скрипт `cleanup_yaml_artifacts.py` (v2)

Line-based (не PyYAML round-trip).

**Применение:**
python scripts/cleanup_yaml_artifacts.py <file.yaml> [...] [--dry-run]

text

Пропускает дубликаты строк в: `preferred_unit_types`, `excluded_unit_types`, `preferred_clause_functions`, `negative_keywords`, `levels`, `preferred_segment_types`, `excluded_segment_types`, `keywords`, `regex_patterns`. Нормализует `.без markdown.` → `. Без markdown.`.

**Не использовать v1** (ломал YAML).

---

## Конец документа v7.5.

**Ближайший шаг нового диалога:**

1. **Changelog v7.3 → v7.4** (в начале документа).
2. Раздел 0 — принципы работы.
3. Раздел 1 — состояние master + uncommitted Stream A.
4. **Раздел 12 — артефакты Stream A.**
5. Раздел 4 — открытый backlog.
6. Раздел 10 — команды старта.

**Рекомендуемый первый шаг:**

1. `git status --short playbooks/global_checks/` — проверить 13 файлов.
2. `python scripts/audit_global_checks.py --summary-only` — убедиться DEEP ⚠️ = 0.
3. Commit Stream A → перекомпиляция playbook в БД → runtime-верификация.
4. Далее — `Layer 2.2` или ревью юриста.
