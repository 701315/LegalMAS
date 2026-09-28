# Обновлённый промт v3 — `docs/TASK_CHECK_CALIBRATION_DOC_TYPE_v3.md`

```markdown
# Задача: Унифицированный анализ DOC-TYPE checks (v3)

**Область:** ТОЛЬКО playbooks/document_types/*
**Создано:** 2026-09-27 (v3 — выравнен по эталону `contract_1.1_general_sale.yaml`)
**Контекст:** B7.10 (presence_signal) + Wave 3 (Layer 2 bulk-roll) + принцип DD Grid «missing visible»
**Master HEAD:** 92666c9
**В scope:** 759 checks в 42 файлах (748 без presence_signal; 11 в contract_1.1 — Батч 1 закрыт)

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

## ЧАСТЬ 0. ЧТО МЫ УЖЕ ЗНАЕМ

### Из Stream A (global checks)

- Пройдены все 44 global checks. 27 YAML-правок в 13 файлах.
- Создан `scripts/audit_global_checks.py` (v3).
- Все правки — в master, протестированы на runtime (run aada2456).

### Классы багов (применимы и к doc-type)

1. **Литеральные placeholder'ы** (`<STATUS_FIELD>`, `<PREFIX>`) — следы шаблонизации.
2. **Дубли bullet'ов** в `<context_rules>`.
3. **Дубли в служебных списках** (`retrieval.preferred_*`, `enrichment_hints.*`).
4. **Опечатки** в `description`.
5. **Порядок тегов инвертирован** — в global checks `<context_rules>` идёт ДО `<context>` (эталон CoC). Часто наоборот.

### Ключевые концепции — стандарт

1. **`missing` vs `unclear`:**
   - `missing` = регулирования нет / фрагментов по теме нет.
   - `unclear` = тексты по теме есть, но вывод сделать нельзя.
   - **Никогда не использовать `unclear` при полном отсутствии фрагментов.**

2. **`present` при прямом исключении** — если договор прямо исключает условие с цитатой → status = `present`. Семантика: present = есть регулирование.

3. **Fallback vs missing** — «Не установлено» в display-поле — это UI-текст, при этом status = `missing`.

4. **`risk_weight` только для `presentation: "signal"`** — не для `fact` и `diagnostic`.

5. **Контракт presence_signal:** union всех трёх групп = allowed_values(field).

### Anti-patterns

- Не менять обязательные поля без явного запроса.
- Не «исправлять» структурные аномалии — только `[CONSIDER]`.
- Не использовать `[UNCERTAIN]` как отговорку.
- Не смешивать global и doc-type checks в одном батче.

---

## ЧАСТЬ 1. ЭТАЛОНЫ

1. **Полностью оформленный GLOBAL check** (для справки):
   ```
   playbooks/global_checks/coc/coc_change_of_control_regime.yaml
   ```

2. **Эталонный DOC-TYPE файл после правок** (главный ориентир стиля!):
   ```
   playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml
   ```
   11 checks с presence_signal. Смотри его как образец всего: расположения `presence_signal`, стиля Layer 2 prompt, дифференциации `risk_weight`, 4-х сценариев `<edge_cases>`, `<output_expectations>`.

3. **Модель Pydantic:**
   ```
   src/engine/playbook/models.py
   ```
   Классы: `CheckDefinition`, `ExtractionConfig`, `ExtractionFieldConfig`, `PresenceSignalConfig`.

---

## ЧАСТЬ 2. СПЕЦИФИКА DOC-TYPE CHECKS

- `rules.keywords`: **flat list**.
- Layer 1 prompt: `llm.prompt_template: |` — **inline, многострочный**. НЕ `prompt_file`.
- `origin: "DOCUMENT_TYPE"` — **обязательно**.
- `triggers: {}` или словарь — **обязательно**.
- `doc_types:` — список конкретных типов.

⚠️ **НЕ меняй эти пять структурных особенностей.**

⚠️ **В одном doc-type файле может быть МНОГО checks.** Анализируй каждый check отдельно, но сохраняй целостность файла.

---

## ЧАСТЬ 3. ГЛАВНЫЙ ПРИНЦИП — «MISSING VISIBLE IN DD GRID»

**Каждый field_extraction check должен явно различать три состояния темы: `present` / `missing` / `unclear`. Каждое из трёх состояний должно быть видно в DD Grid.**

### Семантическая цепочка

```
extraction.presence_signal.field = "<check_id>_presence"
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
display_text ← из *_details / *_display:
  present → конкретные данные
  missing → "Не установлено" / "Данные не определены"
  unclear → "Не удалось определить"
```

### Следствие для Task A

**Для всех 42 doc-type checks — presence_signal ОБЯЗАТЕЛЕН.** Опциональных нет.
Обоснование: пользователь DD Grid должен видеть `missing` **всегда**, когда темы нет.

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
- `extraction.fields[*].risk_weight` — только для полей с `presentation: "signal"`. Дифференцированно: `high` / `medium` / `low` / `info` (см. ЧАСТЬ 6).
- `extraction.fields[*]` — новое поле `<check_id>_presence` (см. ЧАСТЬ 6, Task A).
- `<edge_cases>` в `extraction.llm_prompt_extraction` — если отсутствует.
- `extraction.llm_max_tokens` — только если новый prompt не влезает в старый лимит.

### Может менять (с оговорками)

- `extraction.llm_prompt_extraction` — Layer 2 prompt: выравнивание по эталону (ЧАСТЬ 6, Task B).
- `extraction.fields[*].allowed_values` — только если контракт presence_signal требует (union = allowed_values).

### ⚠️ НЕ добавлять `<location_instructions>`

**В эталоне `contract_1.1_general_sale.yaml` блока `<location_instructions>` НЕТ.** Технический формат JSON (value / confidence / location) задан **отдельным контрактом**. В `<output_expectations>` вместо этого блока идёт одна строка:

```
- Технический формат JSON (value / confidence / location) задан отдельным контрактом — соблюдай его, но не описывай здесь.
```

Это ключевое отличие v3 от v2. **Не придумывать `<location_instructions>`, не включать `location` в список возвращаемых ключей.**

---

## ЧАСТЬ 6. ТРИ ЗАДАЧИ

### Задача A: B7.10 — presence_signal (обязателен для всех)

Для каждого check'а добавить `extraction.presence_signal` — **без исключений**.

**Расположение в YAML (точно как в эталоне):**

```yaml
extraction:
  enabled: true
  mode: "hybrid"
  llm_max_tokens: NNNN

  compact_output: false

  presence_signal:
    field: "<check_id>_presence"
    present_values: ["present"]
    missing_values: ["missing"]
    unclear_values: ["unclear"]

  llm_prompt_extraction: |
    ...

  fields:
    ...
```

⚠️ `presence_signal` идёт **после `compact_output`**, **до `llm_prompt_extraction`**.
⚠️ Не перед `fields`, не в начале секции.

**Плюс** добавить само поле — **первым** в `extraction.fields`:

```yaml
- name: "<check_id>_presence"
  type: "string"
  presentation: "signal"
  risk_weight: "info"
  allowed_values: ["present", "missing", "unclear"]
  display_in_grid: false
  description: "Наличие регулирования по <теме check'а>. Внутреннее агрегатное signal-поле."
  required: true
```

**Контракт:**
- field объявлен в `fields`.
- Три группы попарно disjoint.
- Union всех трёх = `allowed_values(field)`.

**Правило агрегации — в `<task>` как п.0:**

```
0. <check_id>_presence:
   Агрегатное signal-поле — наличие регулирования по теме.
   - "present" — если хотя бы одно из содержательных полей
     (<field1>, <field2>, ...) ≠ "not_defined";
   - "missing" — если все N содержательных полей = "not_defined";
   - "unclear" — если фрагменты по теме есть, но из-за противоречий
     вывод невозможен.

   Если presence = "missing":
   - <field1> = "not_defined";
   - ...
   - все *_details / *_display = соответствующий fallback;
   - не выполняй остальные шаги.
```

**Правило агрегации — в `<context_rules>` (первыми bullet'ами):**

```
- Перед остальными полями заполни <check_id>_presence по правилу из пункта 0 task.
- Если фрагментов по теме нет — presence = "missing"; не используй "unclear" при полном отсутствии фрагментов.
- Если presence = "missing" — все *_status = "not_defined", все *_details/*_display = соответствующий fallback.
```

### Задача B: Wave 3 — Layer 2 bulk-roll

#### B1. `risk_weight` — дифференцированно

Значения: `high` / `medium` / `low` / `info`.

**Правила распределения (по эталону `contract_1.1_general_sale.yaml`):**

| Тип поля | risk_weight |
|---|---|
| presence (агрегатное) | `info` |
| основной status/moment substantive-темы | `high` |
| вторичный status (mode / place / alignment / basis) | `medium` |
| вспомогательный status (accessories / docs) | `low` |

**Пример из эталона (`delivery_and_transfer_docs`):**
- `delivery_term_status` → high
- `delivery_mode` / `delivery_place_status` / `transfer_documents_status` → medium
- `accessories_status` / `product_documents_status` → low

**Пример из эталона (`payment_terms`):**
- `payment_procedure_status` / `payment_model` / `late_payment_consequences_status` → high
- `vat_status` → medium

**Не ставить всем signal-полям `info`** — это упрощение из v2, не соответствующее эталону.

#### B2. Layer 2 prompt — порядок тегов

**Строгий порядок (эталон):**

```
<role> ... </role>

<context>
{context}
</context>

<task>
0. <check_id>_presence: ...
1. ...
2. ...
</task>

<context_rules>
- Перед остальными полями заполни <check_id>_presence ...
- ...
</context_rules>

<edge_cases>
1. Полное отсутствие темы.
2. Прямое исключение или явное отсутствие.
3. Противоречие между фрагментами.
4. Отсылка на внешний документ / неполное раскрытие.
</edge_cases>

<output_expectations>
- Все свободные текстовые поля заполняй на русском языке.
- Для <check_id>_presence используй только: "present", "missing", "unclear".
- Для status-полей используй только: "defined" или "not_defined".
- ...
- Fallback при отсутствии данных: ...
- Fallback при противоречии или неоднозначности: ...
- Технический формат JSON (value / confidence / location) задан отдельным контрактом — соблюдай его, но не описывай здесь.
</output_expectations>
```

⚠️ **`<edge_cases>` между `<context_rules>` и `<output_expectations>`** — не раньше, не позже.
⚠️ **Никаких `<location_instructions>`.**

#### B3. `<edge_cases>` — 4 сценария

Структура (по эталону `contract_1.1_general_sale.yaml`):

Всегда 4 сценария. Первый — универсальный, остальные — подбираются
под тему check'а. Обязательный набор покрытия:

1. Полное отсутствие темы.
   → presence = "missing"; все *_status = "not_defined";
     все *_details/*_display = соответствующий fallback.

2. Неполное раскрытие темы (общая фраза без конкретики,
   согласование в будущем, модель не раскрыта — выбирается по теме check'а).
   → presence = "present"; соответствующие поля = "not_defined".

3. Противоречие между фрагментами.
   → presence = "unclear"; соответствующий *_status = "not_defined";
     соответствующий *_details/*_display = "Не удалось определить".

4. Специфика темы check'а (прямое исключение, отсылка на внешний
   документ, комбинированная ситуация — выбирается по смыслу темы).
   → поведение задаётся отдельно под тему.

См. эталонный файл `contract_1.1_general_sale.yaml` — там 5 checks
с разными наборами сценариев. Не копировать категории слепо,
подбирать под юридическую специфику темы.

#### B4. `<output_expectations>` — обязательная финальная строка

Последней строкой `<output_expectations>` **всегда** идёт:

```
- Технический формат JSON (value / confidence / location) задан отдельным контрактом — соблюдай его, но не описывай здесь.
```

Никаких описаний структуры location-объекта, никаких списков возвращаемых ключей с `location`.

### Задача C: RF-checklist — самопроверка

Перед показом check'а юристу — прогнать через **10 red-flag проверок** (ЧАСТЬ 7). Если хотя бы одна не проходит — исправить и указать в анализе.

---

## ЧАСТЬ 7. RF-CHECKLIST ДЛЯ DOC-TYPE

| ID | Проверка | Что искать |
|---|---|---|
| **RF1** | «Нет фрагментов» → `missing`, не `unclear` | В `<context_rules>` и `<edge_cases>` при отсутствии фрагментов: агрегатное `presence` должно быть `missing`. |
| **RF2** | `not_defined` в существующих status-полях различает «не найдено» и «прямо исключено» | Если договор прямо исключает условие — `not_defined` + `location` с цитатой (в output-контракте). Если просто не раскрыто — `location = null`. |
| **RF3** | Агрегатор `presence` учитывает `location` для `not_defined` | Если status-поле = `not_defined`, но `location` с цитатой — `presence` может быть `present`. |
| **RF4** | Edge cases не содержат оценки риска | Нет фраз «риск не хеджирован», «существенный риск». |
| **RF5** | Display строится ТОЛЬКО из полей | В примерах `*_display` / `*_details` — не должно быть данных, которых нет в полях. |
| **RF6** | `<context_rules>` ведёт к `missing` при отсутствии информации | Если ни один фрагмент не содержит тему — `presence = "missing"`. |
| **RF7** | Нет дублей в `<context_rules>` | Нет двух пунктов про definitions/preamble, про «нет фрагментов». |
| **RF8** | `severity_if_fail` vs `severity` — mismatch задокументирован | Если `severity_if_fail != severity` — пометить `[CONSIDER] as designed`. |
| **RF9** | `description` не противоречит `<role>` | Если `description` обещает «оценку риска», а `<role>` запрещает — `[CONSIDER]`. |
| **RF10** | `presence_signal` расположен корректно + нет `<location_instructions>` | `presence_signal` — после `compact_output`, до `llm_prompt_extraction`. `<location_instructions>` — отсутствует. `<output_expectations>` содержит финальную строку про отдельный контракт. |

**Формат вывода RF-проверки:**

```
## RF-проверка

| RF | Статус | Комментарий |
|---|---|---|
| RF1 | ✅ / ⚠️ / n/a | ... |
| ... | ... | ... |
```

---

## ЧАСТЬ 8. ДОПОЛНИТЕЛЬНЫЕ ЗАДАЧИ (DEEP-аудит)

- **Поиск placeholder'ов** в `<task>` / `<context_rules>`.
- **Поиск дублей** bullet'ов в `<context_rules>`.
- **Поиск дублей** в служебных списках (`retrieval.preferred_*`, `enrichment_hints.*`).
- **Порядок тегов Layer 2:** `<role> → <context> → <task> → <context_rules> → <edge_cases> → <output_expectations>` — если инвертирован, фиксировать `[CONSIDER]`.
- **Опечатки** в `description` и `<role>` (частый баг: `без markdown.без markdown.` в Layer 1).
- **`compact_output: false`** — необычное значение. Фиксировать как `[CONSIDER]`, не менять.

**Пометки:** `[CONSIDER]` — может быть by design; `[DEFER]` — непонятно; `[IGNORE]` — не критично.

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
- Layer 2 prompt: соответствует эталону / частично / нет
- Расположение presence_signal: корректно / инвертировано / отсутствует

## 3. Обязателен ли пункт?

presence_signal обязателен (принцип «missing visible in DD Grid»).

## 4. Предлагаемые изменения

### Изменение 1: добавить presence_signal
БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ
ПРОВЕРКА КОНТРАКТА:
- field объявлен в fields: да
- Попарно disjoint: да
- Union = allowed_values: да

### Изменение 2: добавить risk_weight (дифференцированно)
БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ
(таблица: поле → presentation → risk_weight → обоснование)

### Изменение 3: выровнять Layer 2 prompt по эталону
БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ
(порядок тегов, edge_cases 4 сценария, output_expectations с финальной строкой про отдельный контракт, НЕТ location_instructions)

### Изменение 4: правило агрегации presence
Добавляемый блок в <task> п.0 + первые bullet'ы <context_rules>.

## 5. Дополнительные находки (DEEP-аудит)
- placeholder'ы: ...
- дубли: ...
- порядок тегов: ...
- опечатки: ...
- compact_output: ...
Пометки: [CONSIDER] / [DEFER] / [IGNORE]

## 6. ЧЕК-ЛИСТ СОХРАНЕНИЯ ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ
- [ ] Структурные поля без изменений
- [ ] retrieval.* без изменений
- [ ] rules.keyword_mode, структура keywords (flat)
- [ ] rules.regex_patterns, clause_patterns без изменений
- [ ] enrichment_hints.*, evidence.* без изменений
- [ ] llm.prompt_template (Layer 1 inline) без изменений
- [ ] llm.context_k, temperature, max_tokens без изменений
- [ ] extraction.enabled, mode, compact_output без изменений
- [ ] extraction.fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required без изменений (кроме новых полей)

## 7. RF-проверка
| RF | Статус | Комментарий |

## 8. Финальный YAML (для копипасты после апрува)
<полный YAML check'а с изменениями, структура точно как в contract_1.1_general_sale.yaml>

## 9. ВЕРДИКТ ЮРИСТА
- Изменение 1 (presence_signal): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 2 (risk_weight): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 3 (Layer 2 prompt): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Изменение 4 (правило агрегации): [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ___
- Дополнительные находки: [ ] APPLY NOW / [ ] DEFER / [ ] IGNORE
```

---

## ЧАСТЬ 10. ПЛАН БАТЧЕЙ

**Всего:** 42+ checks в 43 файлах, 9 групп.

**Пилот (Батч 2):** `contract_1.2_retail_sale.yaml` — 14 checks (3 батча по 4–5).
Проверить реальную трудоёмкость на одном файле.

**Батч 1 закрыт:** `contract_1.1_general_sale.yaml` — 11/11 checks с presence_signal, в master с c132372.

**Остаток:** 748 checks в 41 файле. Средний размер файла — ~18 checks.
При 4–5 checks/батч: ~150+ батчей. Реальная оценка — 500+ часов ручной работы.

**Стратегии после пилота:**
- A — ручной по промту (максимальный контроль, 500+ часов).
- B — bulk-скрипт presence_signal/risk_weight + ручная калибровка сложных (50–80 часов).
- Решение по результатам пилота.

**Первый файл для старта пилота:** `contract_1.2_retail_sale.yaml`

**Внутри батча:** 4–5 checks из 1 файла. Один check = один полный блок анализа.

**Если в файле больше 5 checks:** файл разбивается на партии по 4–5 checks.

**Пример для файла с 11 checks:** 3 батча — 4 + 4 + 3.
**Пример для файла с 25 checks:** 5–6 батчей — по 4–5 checks.

---

## Двухшаговый паттерн подачи (обязателен)

### Шаг 1 — обзор файла (контекст)
Юрист даёт **полный набор checks из одного файла**.
Нейросеть:
- читает файл целиком,
- собирает список checks с их id и name,
- НЕ делает правок,
- подтверждает, что файл прочитан, и запрашивает 5 checks для детальной работы.

### Шаг 2 — детальный анализ 5 checks
Юрист даёт **5 checks из уже показанного файла**.
Нейросеть:
- по каждому из 5 checks выдаёт полный блок анализа по ЧАСТИ 9,
- останавливается и ждёт вердикта.

### Шаг 3 — следующий батч
После вердикта:
- нейросеть генерирует финальные YAML для 5 checks,
- юрист применяет правки,
- юрист даёт следующие 5 checks.

### Размер батча
- **4–5 checks** — стандарт для doc-type.
- **6–7 checks** — допустимо для однотипных простых.
- **Больше 7** — запрещено.

### Запрет
Не переходить к следующему батчу без вердикта юриста.
Не смешивать checks из разных файлов в шаге 2.

---

## ЧАСТЬ 12. КОМАНДЫ ДЛЯ СТАРТА

```bash
cd /srv/steloom-dev
source .venv/bin/activate
export PYTHONPATH=src:.

# 1. Handover
head -250 docs/HANDOVER_v7.3.md

# 2. ЭТАЛОННЫЙ файл — читать первым!
cat playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml

# 3. Scope
find playbooks/document_types/ -name "*.yaml" -type f | sort

# 4. Сборка checks из одного файла
python3 << 'PYEOF'
import yaml
from pathlib import Path
p = Path('playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml')
d = yaml.safe_load(p.read_text(encoding='utf-8'))
checks = d.get('checks_v8') or d.get('checks') or []
print(f"Checks in {p.name}: {len(checks)}")
for c in checks:
    print(f"  - {c.get('id')}: {c.get('name')}")
PYEOF

# 5. Проверка YAML после правки
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
10. `[UNCERTAIN]` с догадкой.
11. Брать checks из `playbooks/global_checks/*`.
12. Использовать `unclear` там, где должно быть `missing` (RF1).
13. Оставлять `not_defined` без различения «не найдено» vs «прямо исключено» (RF2).
14. Добавлять в display данные, которых нет в полях (RF5).
15. Допускать противоречие `description` ↔ `<role>` без пометки `[CONSIDER]` (RF9).
16. «Исправлять» структурные аномалии (порядок тегов, `compact_output`) — только `[CONSIDER]`.
17. **Добавлять `<location_instructions>`** — не существует в эталоне, формат задан отдельным контрактом. (RF10)
18. **Включать `location` в список возвращаемых ключей** — не соответствует эталону. (RF10)
19. **Ставить всем signal-полям `risk_weight: "info"`** — эталон требует дифференциации (`high`/`medium`/`low`/`info`). (Задача B1)
20. **Располагать `presence_signal` в начале `extraction:`** — только после `compact_output`, до `llm_prompt_extraction`. (Задача A)
21. Не брать в работу `contract_1.1_general_sale.yaml` — Батч 1 уже закрыт (11/11 checks с presence_signal, в master с c132372).

---

## ПЕРВЫЙ ШАГ

1. Прочитай handover + эталонный `contract_1.1_general_sale.yaml` + reference-файлы.
2. Собери список 42+ doc-type checks в 43 файлах.
3. Выведи план разбивки на батчи (ЧАСТЬ 10).
4. **Шаг 1 паттерна:** дождись от юриста полного набора checks из файла для обзора.
5. **Шаг 2 паттерна:** дождись от юриста 5 checks для детальной работы. Сделай **Батч 1** — 4–5 checks, по формату ЧАСТИ 9.
6. Стоп, жди вердикта юриста по каждому изменению.
7. После CONFIRM/CORRECT — сгенерируй финальные YAML, дождись следующих 5 checks.

**Не начинай правки в YAML до валидации юристом.**
```

---

## Что изменилось в v3 (сводка)

| # | Пункт | v2 | v3 |
|---|---|---|---|
| 1 | `<location_instructions>` | требовалось добавлять | **запрещено** (RF10) |
| 2 | `location` в output | требовалось | **запрещено** (RF10) |
| 3 | Финальная строка output_expectations | не было | **обязательна** (про отдельный контракт) |
| 4 | Порядок тегов Layer 2 | без edge_cases | `<role> → <context> → <task> → <context_rules> → <edge_cases> → <output_expectations>` |
| 5 | `<edge_cases>` | 3–4 примера произвольно | **строго 4 типовых сценария** |
| 6 | `presence_signal` расположение | не фиксировано | **после `compact_output`, до `llm_prompt_extraction`** |
| 7 | `risk_weight` | «всем `info`» | **дифференцированно** (`high`/`medium`/`low`/`info`) |
| 8 | Секция 3 анализа | правовое обоснование | одна строка про принцип DD Grid |
| 9 | Эталонный файл | CoC (global) | **`contract_1.1_general_sale.yaml`** (doc-type после правок) |

## Следующий шаг

Скажите, что делать дальше:

1. **Сохранить v3 как `docs/TASK_CHECK_CALIBRATION_DOC_TYPE_v3.md`** — вы сделаете это сами.
2. **Переписать 5 checks Батча 1** в стиле v3 — я готов начать с `seller_identification_cluster` как образца.
3. **Что-то поправить в v3** — какие-то пункты считаете лишними или неполными.