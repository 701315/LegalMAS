```markdown
# Задача: Унифицированный анализ DOC-TYPE checks (v2)

**Область:** ТОЛЬКО playbooks/document_types/*
**Создано:** 2026-09-26 (v2 после Stream A по global checks)
**Контекст:** B7.10 (presence_signal) + Wave 3 (Layer 2 bulk-roll) + принцип DD Grid «missing visible»
**Master HEAD:** (уточнить в новом диалоге)
**В scope:** 42 doc-type field_extraction checks в 43 файлах

## Как работать с этим файлом

1. Открыть НОВЫЙ диалог с нейросетью.
2. Скопировать содержимое этого файла целиком в первое сообщение.
3. Нейросеть читает контекст, собирает список checks, выводит план батчей.
4. Нейросеть делает Батч 1 (4-5 checks). Стоп, показывает.
5. Юрист CONFIRM/REJECT/CORRECT по каждому изменению.
6. Возврат в диалог → следующий батч.
7. После всех checks — коммит через git workflow.

**Не начинать правки YAML до валидации юристом.**

---

## ПРАВИЛО ИЗОЛЯЦИИ — читать первым

⚠️ Ты работаешь ТОЛЬКО с checks из playbooks/document_types/*.

- Никогда не бери в работу checks из playbooks/global_checks/*.
- Никогда не смешивай doc-type и global checks в одном батче.
- Если по ошибке взял check не из своей области — останови работу и сообщи пользователю.
- Отдельный промт существует для playbooks/global_checks/* — это НЕ он.

---

## ЧАСТЬ 0. ЧТО МЫ УЖЕ ЗНАЕМ ИЗ ПРЕДЫДУЩЕЙ СЕССИИ (Stream A — global checks)

В предыдущей сессии отработан аналогичный рефакторинг для 44 global checks.
Итоги и уроки — критичны для doc-type:

### Что было сделано (global checks)

- Пройдены все 44 global checks.
- 27 YAML-правок в 13 файлах.
- Создан `scripts/audit_global_checks.py` (v3) — трёхуровневый аудит.
- Создан `docs/CONSIDER_PACKAGE_v1.md` — 19 пунктов для юриста.
- Все правки — в master, протестированы на runtime (run aada2456).

### Найденные классы багов (применимы и к doc-type)

1. **Литеральные placeholder'ы** (`<STATUS_FIELD>`, `<PREFIX>`) — следы шаблонизации. LLM видит буквальную строку и не понимает адресата правила. Найдены в 7 global checks.
2. **Дубли bullet'ов** в `<context_rules>` — правило «нет фрагментов → missing» повторено дважды.
3. **Дубли в служебных списках** (`retrieval.preferred_clause_functions`, `preferred_unit_types`, `enrichment_hints.*`) — артефакт копипаста.
4. **Опечатки** в `description` (например, `налиличие`).
5. **Порядок тегов инвертирован** — в global checks `<context_rules>` должен идти ДО `<context>` (эталон CoC). Часто наоборот.

### Ключевые концепции, которые теперь стандарт

1. **`missing` vs `unclear`** — принципиальное различие:
   - `missing` = регулирования нет / фрагментов по теме нет.
   - `unclear` = тексты по теме есть, но вывод сделать нельзя.
   - **Никогда не использовать `unclear` при полном отсутствии фрагментов.**

2. **`present` при прямом исключении** — если договор прямо исключает условие («Non-compete не применяется») с цитатой → status = `present`, потому что регулирование есть. Семантика: present = есть регулирование, а не present = есть защита.

3. **Fallback vs missing** — «Не установлено» в display-поле — это UI-текст, а status при этом `missing`. Не путать.

4. **`risk_weight` только для `presentation: "signal"`** — не для `fact` и `diagnostic`.

5. **Контракт presence_signal:** union всех трёх групп = allowed_values(field). Если `unclear_values` пустой — формально допустимо, но семантически ограничивает.

### Anti-patterns, которых избегаем

- Не менять обязательные поля без явного запроса.
- Не «исправлять» структурные аномалии (порядок тегов, `compact_output: false`) — только фиксировать как `[CONSIDER]`.
- Не использовать `[UNCERTAIN]` как отговорку — если не знаешь, не гадай.
- Не смешивать global и doc-type checks в одном батче.

---

## ЧАСТЬ 1. ЭТАЛОНЫ — три reference-файла

1. **Полностью оформленный GLOBAL check** (для справки по формату presence_signal/risk_weight/Layer 2):
   ```
   playbooks/global_checks/coc/coc_change_of_control_regime.yaml
   ```

2. **Эталонный DOC-TYPE check** с уже развитым Layer 2 prompt, но без presence_signal:
   ```
   playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml
   ```
   Ищи check `parties_and_authority` — это образец по структуре.

3. **Модель Pydantic:**
   ```
   src/engine/playbook/models.py
   ```
   Классы: `CheckDefinition`, `ExtractionConfig`, `ExtractionFieldConfig`, `PresenceSignalConfig`.

---

## ЧАСТЬ 2. СПЕЦИФИКА DOC-TYPE CHECKS (отличается от global!)

- `rules.keywords`: **flat list**. Например:
  ```yaml
  rules:
    keyword_mode: any
    keywords:
      - "продавец"
      - "покупатель"
      - "в лице"
  ```

- Layer 1 prompt: `llm.prompt_template: |` — **inline, многострочный**. НЕ `prompt_file`.

- `origin: "DOCUMENT_TYPE"` — **обязательно присутствует**.

- `triggers: {}` или словарь — **обязательно присутствует**.

- `doc_types:` — **список конкретных типов**, например `[contract_1.1_general_sale]`.

⚠️ **НЕ меняй эти пять структурных особенностей.** Если увидишь отклонение — фиксируй в дополнительных находках, не «исправляй» автоматически.

⚠️ **ВАЖНО: в одном doc-type файле может быть МНОГО checks** (например, `contract_1.1_general_sale.yaml` содержит 11 checks; в других файлах — до 30+). Анализируй каждый check отдельно, но сохраняй целостность файла при правках.

---

## ЧАСТЬ 3. ГЛАВНЫЙ ПРИНЦИП — «MISSING VISIBLE IN DD GRID»

### Формулировка принципа

**Каждый field_extraction check должен явно различать три состояния темы в документе: `present` / `missing` / `unclear`. Каждое из трёх состояний должно быть видно в DD Grid.**

### Семантическая цепочка

```
extraction.presence_signal.field = "<prefix>_status"
        │
        ▼
LLM возвращает value ∈ {present, missing, unclear}
        │
        ▼
CheckResult.result ← маппинг по presence_signal:
  present_values  → result = pass
  missing_values  → result = missing_required_clause
  unclear_values  → result = unclear
        │
        ▼
DD Grid рендерит:
  pass                     → зелёная строка + LOCATION
  missing_required_clause  → "clause_missing", LOCATION = "—"
  unclear                  → "clause_unclear", LOCATION = "—"
        │
        ▼
display_text ← из *_display / *_details поля:
  present → конкретные данные ("RUB; постоплата; пени 0,05%")
  missing → "Не установлено" / "Данные не определены" / "Не обнаружено"
  unclear → "Не удалось определить"
```

### Следствие для Task A

**Было (устаревшее ТЗ):**
> Обязателен → добавить presence_signal.
> Опционален → оставить как есть.

**Стало (обновлённое):**
> **Для всех 42 doc-type checks — presence_signal ОБЯЗАТЕЛЕН.** Опциональных нет.
> Обоснование: пользователь DD Grid должен видеть `missing` **всегда**, когда темы нет в документе. Это не задача об «обязательности пункта в договоре» — это задача о **видимости статуса в интерфейсе**.

### Верификация принципа

На run `aada2456` (пример):
- `coc_change_of_control_regime` → `missing_required_clause` + «Положения о смене контроля не установлены» + LOCATION = —
- `aml_kyc` → `missing_required_clause` + «AML/KYC не обнаружены» + LOCATION = —
- `governing_law_and_forum` → `pass` + «Применимое право: РФ; Форум: не указан» + LOCATION = p.7 · main_contract:11

**Принцип работает для global checks.** Для doc-type — не работает, потому что `presence_signal` отсутствует.

---

## ЧАСТЬ 4. ОБЯЗАТЕЛЬНЫЕ ПОЛЯ — НЕ ТРОГАТЬ

Код читает эти поля. Их изменение может сломать pipeline.

- **Структурные:** `id, name, description, doc_types, origin, group, severity, severity_if_pass, severity_if_fail, severity_if_unclear, detector_type, ui_mode, triggers, conditional, store_payload`
- **Retrieval (вся секция):** `retrieval_profile, retrieval_query, boost_keywords, negative_keywords, preferred_unit_types, excluded_unit_types, preferred_clause_functions, position_bias, rerank, filters, corpus_scope, levels, required_kind, context_k, max_chunks`
- **Rules:** `keyword_mode, структура keywords (flat), regex_patterns, clause_patterns`
- **Enrichment / Evidence:** `enrichment_hints.*, evidence.*`
- **LLM Layer 1:** `prompt_template (inline), context_k, temperature, max_tokens`
- **Extraction:** `enabled, mode, compact_output, fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required`

---

## ЧАСТЬ 5. ЧТО AI МОЖЕТ ДОБАВЛЯТЬ/МЕНЯТЬ

### Может добавлять

- `extraction.presence_signal` — всегда, для каждого check'а.
- `extraction.fields[*].risk_weight` — только для полей с `presentation: "signal"`.
- `<location_instructions>` в `extraction.llm_prompt_extraction` — если отсутствует.
- `<output_expectations>` в `extraction.llm_prompt_extraction` — если отсутствует или в плоском формате.
- `<edge_cases>` в `extraction.llm_prompt_extraction` — если отсутствует.
- Few-shot примеры в `<output_expectations>`.
- `extraction.llm_max_tokens` — только если новый prompt не влезает в старый лимит.

### Может менять (с оговорками)

- `extraction.llm_prompt_extraction` — Layer 2 prompt.
- `extraction.fields[*].allowed_values` — только если контракт presence_signal требует (union = allowed_values).

---

## ЧАСТЬ 6. ТРИ ЗАДАЧИ

### Задача A: B7.10 — presence_signal (обязателен для всех)

Для каждого check'а добавить `extraction.presence_signal` — **без исключений**.

**Формат (эталон — CoC):**
```yaml
extraction:
  presence_signal:
    field: "<check_id>_presence"
    present_values: ["present"]
    missing_values: ["missing"]
    unclear_values: ["unclear"]
```

**Плюс** добавить само поле в `extraction.fields`:
```yaml
- name: "<check_id>_presence"
  type: "string"
  presentation: "signal"
  risk_weight: "info"
  allowed_values: ["present", "missing", "unclear"]
  display_in_grid: false
  description: "Наличие регулирования по теме check'а"
  required: true
```

**Контракт:**
- field объявлен в `fields`.
- Три группы попарно disjoint.
- Union всех трёх = `allowed_values(field)`.

**Правило агрегации (добавить в `<task>` и `<context_rules>` prompt'а):**
```
1. Сначала заполни <check_id>_presence:
   - "present" — если хотя бы одно содержательное поле ≠ "not_defined";
   - "missing" — если все содержательные поля = "not_defined";
   - "unclear" — если тексты есть, но вывод невозможен.

2. Если presence = "missing":
   - все содержательные поля = "not_defined";
   - все *_details / *_display = "Не установлено" / "Данные не определены";
   - все location = null;
   - не выполняй остальные шаги.
```

### Задача B: Wave 3 — Layer 2 bulk-roll

1. **`risk_weight`** — добавить в `extraction.fields[*]` для полей с `presentation: "signal"`. Значения: `high / medium / low / info`.

2. **Layer 2 prompt (`extraction.llm_prompt_extraction`)** — должен содержать:
   - **`<location_instructions>`** — что LLM возвращает в location (`clause_ref`, `page`, `quote`).
   - **`<output_expectations>`** — контракт JSON-ответа в формате `{value, confidence, location}`.
   - **`<edge_cases>`** — образцы краевых состояний.
   - Few-shot примеры.

### Задача C: RF-checklist — самопроверка

Перед показом check'а юристу — прогнать через **10 red-flag проверок** (ЧАСТЬ 7). Если хотя бы одна не проходит — исправить и указать в анализе.

---

## ЧАСТЬ 7. RF-CHECKLIST ДЛЯ DOC-TYPE

Применять к **каждому** check'у до показа юристу.

| ID | Проверка | Что искать |
|---|---|---|
| **RF1** | «Нет фрагментов» → `missing`, не `unclear` | В `<edge_cases>` при отсутствии фрагментов: агрегатное `presence` должно быть `missing`. |
| **RF2** | `not_defined` в существующих status-полях различает «не найдено» и «прямо исключено» | Если договор прямо исключает условие — `not_defined` + `location` с цитатой. Если просто не раскрыто — `location = null`. |
| **RF3** | Агрегатор `presence` учитывает `location` для `not_defined` | Если существующее status-поле = `not_defined`, но `location` с цитатой — `presence` может быть `present`. |
| **RF4** | Edge cases не содержат оценки риска | Нет фраз «риск не хеджирован», «существенный риск» и т.п. — только факты. |
| **RF5** | Display строится ТОЛЬКО из полей | В примерах `*_display` / `*_details` — не должно быть данных, которых нет в полях. |
| **RF6** | `<context_rules>` ведёт к `missing` при отсутствии информации | Если ни один фрагмент не содержит тему — `presence = "missing"`, не `unclear` / `not_defined` без обоснования. |
| **RF7** | Нет дублей в `<context_rules>` | Проверить: нет двух пунктов про definitions/preamble, про «нет фрагментов». |
| **RF8** | `severity_if_fail` vs `severity` — mismatch задокументирован | Если `severity_if_fail != severity` — пометить `[CONSIDER] as designed`. |
| **RF9** | `description` не противоречит `<role>` | Если `description` обещает «оценку риска», а `<role>` запрещает — `[CONSIDER]`, не менять `description`. |
| **RF10** | `<location_instructions>` однозначно трактует quote для `not_defined` | Для `not_defined` явно указать: quote обязательна при прямом исключении, `null` — при простом отсутствии. |

**Формат вывода RF-проверки:**
```
## RF-проверка

| RF | Статус | Комментарий |
|---|---|---|
| RF1 | ✅ / ⚠️ / n/a | ... |
| ... | ... | ... |
```

---

## ЧАСТЬ 8. ДОПОЛНИТЕЛЬНЫЕ ЗАДАЧИ ВНЕ A/B/C

Уроки Stream A — проверять в каждом check'е как DEEP-аудит:

- **Поиск placeholder'ов** в `<task>` / `<context_rules>`: `<STATUS_FIELD>`, `<PREFIX>`, `<CHECK_ID>` — всё в квадратных скобках или с ALL_CAPS.
- **Поиск дублей** bullet'ов в `<context_rules>`.
- **Поиск дублей** в служебных списках (`retrieval.preferred_*`, `enrichment_hints.*`).
- **Порядок тегов:** `<context_rules>` должен идти ДО `<context>` — если инвертирован, фиксировать `[CONSIDER]`.
- **Опечатки** в `description` и `<role>`.
- **`compact_output: false`** — необычное значение. Фиксировать как `[CONSIDER]`, не менять.

**Пометки:** `[CONSIDER]` — если может быть by design; `[DEFER]` — если непонятно; `[IGNORE]` — если не критично.

---

## ЧАСТЬ 9. ФОРМАТ ВЫВОДА — для каждого check

```
# Анализ: <check_id>

Файл: <path>
Origin: DOCUMENT_TYPE
Doc types: [список]
UI mode: field_extraction

## 1. Что проверяет check
<1-2 предложения>

## 2. Текущее состояние
- presence_signal: есть / нет / частично
- risk_weight (signal): есть / нет / частично
- Layer 2 prompt (location_instructions): есть / нет
- Layer 2 prompt (output_expectations): есть / нет
- Layer 2 prompt (edge_cases): есть / нет

## 3. Анализ: обязателен ли пункт?
<Для каких типов договоров тема обязательна, обоснование ст. ГК>
Уверенность: высокая / средняя / низкая

## 4. Предлагаемые изменения

### Изменение 1: добавить presence_signal
БЫЛО: ...
СТАЛО: ...
ОБОСНОВАНИЕ: ...
УВЕРЕННОСТЬ: высокая / средняя / низкая
ПРОВЕРКА КОНТРАКТА:
- field объявлен в fields: да
- Попарно disjoint: да
- Union = allowed_values: да

### Изменение 2: добавить risk_weight
БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ
(таблица полей с весами)

### Изменение 3: переработать Layer 2 prompt (location/output/edge_cases)
БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ

### Изменение 4: правило агрегации `presence` в `<task>`
Добавляемый блок в `<task>` и `<context_rules>`.

## 5. Дополнительные находки (DEEP-аудит)
- placeholder'ы: ...
- дубли: ...
- порядок тегов: ...
- опечатки: ...
Пометки: [CONSIDER] / [DEFER] / [IGNORE]

## 6. ЧЕК-ЛИСТ СОХРАНЕНИЯ ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ
- [ ] Структурные поля без изменений
- [ ] retrieval.* без изменений
- [ ] rules.keyword_mode, структура keywords (flat остаётся flat)
- [ ] rules.regex_patterns, clause_patterns без изменений
- [ ] enrichment_hints.*, evidence.* без изменений
- [ ] llm.prompt_template (Layer 1 inline) без изменений
- [ ] llm.context_k, temperature, max_tokens без изменений
- [ ] extraction.enabled, mode, compact_output без изменений
- [ ] extraction.fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required без изменений

## 7. RF-проверка
| RF | Статус | Комментарий |

## 8. Финальный YAML (для копипасты после апрува)
<полный YAML check'а с изменениями>

## 9. ВЕРДИКТ ЮРИСТА
- Изменение 1 (presence_signal): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 2 (risk_weight): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 3 (Layer 2 prompt): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 4 (правило агрегации): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Дополнительные находки: [ ] APPLY NOW / [ ] DEFER / [ ] IGNORE
```

---

## ЧАСТЬ 10. ПЛАН БАТЧЕЙ ПО ГРУППАМ

**Всего:** 42+ checks в 43 файлах, 9 групп:

| Батч | Группа | Файлов | Примерный объём |
|---|---|---|---|
| **1 (пилот)** | group_1_ownership | 1–2 файла, 4–5 checks | калибровка |
| 2–4 | group_1_ownership (продолжение) | 12 файлов, ~15 checks | ~30 часов |
| 5 | group_2_use (lease, rental, vehicle lease, leasing) | 4 файла | ~15 часов |
| 6 | group_3_works + group_4_services | 8 файлов | ~20 часов |
| 7 | group_5_financial + group_6_intermediary | 8 файлов | ~20 часов |
| 8 | group_7_ip + group_8_partnership | 5 файлов | ~15 часов |
| 9 | group_9_special | 5 файлов | ~15 часов |

**Порядок:** начать с group_1 (пилот), затем — по группам.

**Внутри батча:** 4–5 checks из 1 файла. Один check = один полный блок анализа.

**Если в файле больше 5 checks:** файл не подаётся целиком на правку.
Он разбивается на партии по 4–5 checks, которые обрабатываются последовательно
(см. ЧАСТЬ 11 «Двухшаговый паттерн подачи»).

**Пример для файла с 11 checks:** 3 батча — 4 + 4 + 3.
**Пример для файла с 25 checks:** 5–6 батчей — по 4–5 checks.

---

## Двухшаговый паттерн подачи (обязателен)

Каждый батч подаётся в ДВА сообщения:

### Шаг 1 — обзор файла (контекст)
Юрист в первом сообщении даёт **полный набор checks из одного файла**
(или несколько файлов сразу, если они тематически связаны).
Нейросеть:
- читает файл целиком,
- собирает список checks с их id и name,
- НЕ делает правок,
- подтверждает, что файл прочитан, и запрашивает 5 checks для детальной работы.

### Шаг 2 — детальный анализ 5 checks
Юрист во втором сообщении даёт **5 checks из уже показанного файла**
(явно, текстом или через выделение нужных id).
Нейросеть:
- по каждому из 5 checks выдаёт полный блок анализа по ЧАСТИ 9,
- останавливается и ждёт вердикта юриста по каждому изменению.

### Шаг 3 — следующий батч
После вердикта юриста:
- нейросеть генерирует финальные YAML для 5 checks,
- юрист применяет правки,
- юрист даёт следующие 5 checks (из того же файла или из нового).

### Размер батча
- **4–5 checks** — стандарт для doc-type.
- **6–7 checks** — допустимо, только если checks однотипны и просты (например, только `presence_signal` без сложных Layer 2).
- **Больше 7** — запрещено. Даже если в файле 25 checks, они идут партиями по 4–5.

### Почему так
1. **Полный файл в шаге 1** — нейросеть видит общий контекст: как checks
   соотносятся, нет ли дублей, какая структура у файла.
2. **5 checks в шаге 2** — комфортный объём для вдумчивого CONFIRM/REJECT/CORRECT
   без потери деталей.
3. **Разделение анализа и правок** — юрист сначала видит все изменения,
   потом подтверждает, только потом генерируется YAML.

### Запрет
Не переходить к следующему батчу без вердикта юриста по текущему.
Не смешивать checks из разных файлов в одном шаге 2, если файлы тематически разные.

---

## ЧАСТЬ 12. КОМАНДЫ ДЛЯ СТАРТА

```bash
cd /srv/steloom-dev
source .venv/bin/activate
export PYTHONPATH=src:.

# 1. Handover v7.4
head -250 docs/HANDOVER_v7.3.md

# 2. Reference-файлы
cat playbooks/global_checks/coc/coc_change_of_control_regime.yaml
sed -n '/^  - id: parties_and_authority/,/^  - id:/p' \
  playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml | head -300

# 3. Scope — список 43 файлов
find playbooks/document_types/ -name "*.yaml" -type f | sort

# 4. Сборка checks из одного файла (пример)
python3 << 'PYEOF'
import yaml
from pathlib import Path
p = Path('playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml')
d = yaml.safe_load(p.read_text(encoding='utf-8'))
checks = d.get('checks', [])
print(f"Checks in {p.name}: {len(checks)}")
for c in checks:
    print(f"  - {c.get('id')}: {c.get('name')}")
PYEOF

# 5. Аудит placeholder'ов в doc-type (ручной)
grep -rn "<[A-Z][A-Z0-9_]*>" playbooks/document_types/ | grep -v "{{" | head -20

# 6. Проверка YAML после правки
python -c "import yaml; yaml.safe_load(open('<путь>'))"
```

---

## ЧАСТЬ 13. ЧТО НЕ ДЕЛАТЬ

1. Менять обязательные поля без явного запроса.
2. Менять структуру `rules.keywords` (flat ↔ nested).
3. Менять `llm.prompt_template` ↔ `llm.prompt_file`.
4. Убирать `origin` или `triggers`.
5. Менять `retrieval.*`.
6. Придумывать `risk_weight` без обоснования.
7. Менять контракт `presence_signal`.
8. Игнорировать `presentation: "signal"` при добавлении `risk_weight`.
9. Применять правки без ревью юриста.
10. `[UNCERTAIN]` с догадкой — если не знаешь, не гадай.
11. Брать checks из `playbooks/global_checks/*`.
12. Использовать `unclear` там, где должно быть `missing` (RF1).
13. Оставлять `not_defined` без различения «не найдено» vs «прямо исключено» (RF2).
14. Добавлять в display данные, которых нет в полях (RF5).
15. Допускать противоречие `description` ↔ `<role>` без пометки `[CONSIDER]` (RF9).
16. «Исправлять» структурные аномалии (порядок тегов, `compact_output`) — только `[CONSIDER]`.

---

## ПЕРВЫЙ ШАГ

1. Прочитай handover v7.4 + три reference-файла.
2. Собери список 42+ doc-type checks в 43 файлах.
3. Выведи план разбивки на батчи (ЧАСТЬ 10).
4. **Шаг 1 паттерна:** дождись от юриста полного набора checks из файла
   для обзора. Подтверди, что файл прочитан, перечисли checks по id и name.
5. **Шаг 2 паттерна:** дождись от юриста 5 checks для детальной работы.
   Сделай **Батч 1** — 4–5 checks, по формату ЧАСТИ 9.
6. Стоп, жди вердикта юриста по каждому изменению.
7. После CONFIRM/CORRECT — сгенерируй финальные YAML, дождись следующих 5 checks.

**Не начинай правки в YAML до валидации юристом.**
```

---

## Сопроводительная записка к промту

**Что в промте — новое и важное:**

1. **ЧАСТЬ 0** — конспект Stream A. В новом диалоге нейросеть сразу понимает контекст: какие баги уже видели, какие уроки применимы.

2. **ЧАСТЬ 3** — центральный принцип «missing visible in DD Grid». Это меняет формулировку Task A: presence_signal **обязателен для всех 42 checks**, а не «по решению юриста».

3. **ЧАСТЬ 7** — RF-checklist адаптирован под doc-type: `not_defined` вместо `no`, `presence` вместо `has_*_status`, `*_details` вместо `*_display`.

4. **ЧАСТЬ 8** — DEEP-аудит: placeholder'ы, дубли, опечатки, порядок тегов — по аналогии с global.

5. **ЧАСТЬ 10** — план батчей по группам с расчётом объёма. Пользователь понимает, что задача на ~130 часов.

6. **ЧАСТЬ 12** — команды для старта, включая парсинг YAML для извлечения checks из одного файла (это нюанс doc-type — множество checks в одном файле).

**Что нужно сделать с этим промтом:**

1. Сохранить в файл `docs/TASK_CHECK_CALIBRATION_DOC_TYPE_v2.md`.
2. При следующем обновлении Handover v7.4 → v7.5 — добавить ссылку на этот файл.
3. В новом диалоге — скопировать промт целиком в первое сообщение.

**Что можно улучшить после пилота:**

- Если юрист выберет вариант 2 presence_signal (маппинг на существующий `*_status` вместо агрегатного `*_presence`) — переписать ЧАСТЬ 6 и 9.
- Если `[CONSIDER]`-аномалии (порядок тегов, `compact_output`) решено **не трогать вообще** — усилить запрет в ЧАСТИ 13.
- Если объём окажется неподъёмным за 1 сессию — разбить ЧАСТЬ 10 на 3–4 под-сессии (group_1 → groups 2–4 → groups 5–7 → groups 8–9).

Готовы запустить новый диалог?