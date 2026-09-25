# Handover + Plan v7.3 — Steloom

**Дата:** 2026-09-25
**Master HEAD:** `05a72ca`
**Базис:** v7.2 (24.09) + B7.4 + B7.5 + B7.6 + B7.9
**Как использовать:** вставить целиком в первое сообщение нового диалога.

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

---

## Раздел 1. Текущее состояние master

```
master = 05a72ca   [origin/master]
feat/reap-stale-runs = c9afa43   [отложенная, покрыта архивным тегом]

origin/master
origin/feat/reap-stale-runs
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

### Track A — Detection Quality Audit

| Этап | Статус |
|---|---|
| A0 | presence_signal для field_extraction | ✅ DONE (21.09) |
| A1 | Программный аудит (SQL) | ⏳ TODO |
| A2 | Ручной аудит (юрист) | ⏳ TODO (требует юриста) |
| A3 | Аудит YAML | ⏳ TODO (требует юриста + product) |
| A4 | Калибровка порогов | ⏳ TODO (после A2) |
| A5 | Улучшение промптов | ⏳ TODO (после A2+A3) |

**Track A полностью заблокирован на юридический аудит.**

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

## Раздел 3. Отменённые гипотезы (не делать снова)

| Гипотеза | Причина отмены |
|---|---|
| **B7.3** — `detect_toc_block` end_index = `last_entry_i + 1` | 16/18 passed, но 72/335 документов потеряли ToC. Откат. Заменён на B7.4 (State Machine). |
| **B7.7** — synthetic uid в appendix | Docling выдаёт чистые атомы (`marker=None` для `ПРИЛОЖЕНИЯ`, `Приложение № N`). |
| **B7.8** — Docling uid synthesis | Docling корректен. |
| **DoD `quality_completeness_warranty.page=6`** | Снят. Корректное поведение для документа без клаузы о качестве: `page=2, clause_uid=__preamble__` в БД, **LOCATION пустой в UI**. |

**Методический вывод:** каждая отменённая гипотеза была «логически правдоподобной». Отменяли их после аудита данных: PyMuPDF dump PDF, Docling output dump, `git log -L` на функцию.

## Раздел 4. Открытый backlog (что осталось)

### B7.9.1 — fix A: `_resolve_field_location_bundle` (гигиена БД)

**Файл:** `src/engine/checks/extraction.py`, функция `_resolve_field_location_bundle` (строки ~146–170).

**Проблема.** При отсутствии per-field location от LLM подставляет `base_location` (из R15-фолбэка `retrieved_chunks[0]`). В `structured_data.<field>.location_fallback` попадают misleading `check_page=2`, `check_clause_uid=main_contract:__preamble__`.

**Fix.**
```python
if isinstance(location_fallback, dict):
    raw_reason = location_fallback.get("reason")
    if raw_reason and str(raw_reason).strip():
        return None, {"reason": str(raw_reason).strip()}
```
Если caller явно сообщил «не найдено» с reason — honor'ить, не подмешивать `base_location`.

**Blast radius.** 1 функция, 5 строк. 4 unit-теста:
1. `location=dict` → as-is, fallback=None (regression).
2. `location=None`, `location_fallback={"reason": "..."}` → `(None, {"reason": "..."})` **без** `check_page`/`check_clause_uid`.
3. `location=None`, `location_fallback=None` → fallback через base_location (regression).
4. `location=None`, `location_fallback={"reason": ""}` → fallback через base_location (regression).

**Приоритет.** Средний. Не влияет на UI (B7.9 закрыл).

### B7.9.2 — fix B: R15 не заполняет `check_results.page/clause_uid` для field_extraction

**Файл:** `src/engine/checks/executor.py:1209–1233` (R15).

**Проблема.** R15 заполняет `detection["location"]` из `retrieved_chunks[0]`. Оттуда — `check_results.page=2`, `check_results.clause_uid=main_contract:__preamble__` для всех field_extraction checks без LLM anchor.

**Fix.** Для `is_field_extraction` — не merge'ить `retrieval_provenance` в executor (~1581–1590):
```python
if is_field_extraction:
    provenance = detector_provenance
else:
    provenance = self._merge_provenance(detector_provenance, retrieval_provenance)
```

**Риск.** 786 `field_extraction` checks в playbooks. **Требует валидации на 5–10 checks** перед применением.

**Приоритет.** Низкий. UI корректен без него.

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

### 🔴 Волна 3: Layer 2 bulk-roll (3–4 дня)

**44 файла P3b + 7 document_types.**

**Батчи:**
1. `liability/*` (4)
2. `term/*` (4), `coc/*` (2)
3. `rw/*` (4), `finance/*` (4)
4. `sanctions/*` (3), `regulatory/*` (3)
5. `assignment_transfer/*` (3), `ip_it/*` (4)
6. `formal/*` (4), `hr/*` (2), `cyber/*` (2)
7. Остаток

**Шаблон P3b** (согласован в B5.3):
- `<location_instructions>` — после `</task>`.
- `<output_expectations>` — плоский JSON → трёхполевой.
- `fields:` — `risk_weight` для signal + labels.

**Что делаем:** расширить все checks во всех YAML: добавить Layer 2 custom prompt, `risk_weight` для signal-полей, `<location_instructions>`.

### 🔵 Волна 4: B3.6 — layout_element_ids (3–5 дней)

**Цель.** Проброс `layout_elements` через pipeline для точного `element_ids` в `CheckAnchor`.

**Файлы:**
- `src/engine/checks/executor.py` — проброс `layout_elements` в `extraction_contexts`.
- `src/services/structure/chunk_canonicalization.py` — metadata.
- `src/engine/checks/extraction.py::_resolve_field_anchor` — получает `layout_elements`.
- `src/engine/checks/citation_resolver.py` — `_compute_element_offsets` + preamble fix.

### ⚪ Волна 5: B4b + Layer 2.2 (2–3 дня)

1. **B4b** — `anchor_stale` (1–2 дня). Инвалидация anchor'ов при refresh контента.
2. **Layer 2.2** — 7 `document_types/*.yaml` (1 день).

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

# Worker status
tmux list-windows -t steloom-dev -F '#I:#W'
tail -5 /home/steloom/dev-logs/worker-default.log

# БД
sudo docker exec -i mas_dd_postgres psql -U mas -d mas_dd -c "
SELECT id, status, created_at FROM runs ORDER BY created_at DESC LIMIT 5;
"
```

**Первая задача нового диалога — выбор из:**

1. **Волна 3: Layer 2 bulk-roll** — 44 файла P3b + 7 document_types. Механическая работа по батчам.
2. **B3.6 — layout_element_ids** — архитектурная, 3–5 дней, требует проброса через executor → extraction → resolver.
3. **B7.9.1** — fix A (5 строк + 4 теста, гигиена БД). Быстро и точечно.
4. **B7.9.2** — fix B (R15), требует валидации на 5–10 checks.
5. **B7.4.5** — appendix-tail в ToC, опционально.

**Рекомендация:** начать с **B7.9.1** (быстро, гигиена данных) → затем **Волна 3** (mechanically). B3.6 оставить на потом, когда накопится понимание.

---

## Раздел 11. История коммитов (последние 15)

```
05a72ca (tag: post-B7.9-honest-field-anchor-...) Merge branch 'fix/B7.9-honest-field-anchor'
93fac4c fix(dd-grid): B7.9 — structural markers drop page, not just clause_ref
586b425 (tag: post-B7.5-spatial-matcher-...) Merge branch 'feat/B7.5-toc-body-uid-collision'
bce05c8 chore(B7.5): add spatial matcher diagnostics scripts
f5941e9 fix(B7.5): reject geometrically invalid spatial marker matches
929a57c (tag: post-B7.6-toc-zone-filter-...) Merge branch 'feat/B7.6-toc-zone-heading-filter'
d748219 fix(structure): B7.6 — ToC-zone heading filter respects post_toc confirmation
257092c (tag: post-B7.4-toc-state-machine-iter2-...) Merge branch 'feat/B7.4-toc-state-machine' (iteration 2)
3489dc8 feat(structure): B7.4 — TOC State Machine + extended entry criteria
21948c6 (tag: post-B7.1-B7.2-toc-fixes-...) Merge branch 'feat/B7.1-toc-dedup-fix'
2c20e50 test(structure): coverage suite detect_toc_block — 18 кейсов
067f41a fix(structure): B7.2 — структурный фикс ToC-зоны
dfbbd18 feat(structure): B7.1 — body candidate wins over ToC
b61183a (tag: post-B6.3-follow-ups-...) Merge branch 'feat/B6.3-follow-ups'
66e75a5 (tag: post-B6.2-detection-quality-...) Merge branch 'feat/B6.2-detection-quality'
```

---

## Конец документа v7.3.

**Ближайший шаг нового диалога:**

1. Прочитать Раздел 0 — принципы работы (аудит → 100% → продакшн).
2. Раздел 1 — состояние master.
3. Раздел 4 — открытый backlog, выбор задачи.
4. Раздел 6 — окружение.
5. Раздел 10 — команды старта.
6. Раздел 9 — уроки (не повторять ошибки).

**Ключевое правило:** перед любой правкой — аудит до 100% понимания. Только потом — продакшн-фикс.
