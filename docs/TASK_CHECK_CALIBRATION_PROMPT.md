# Инструкция по использованию этого файла

**Создано:** 2026-09-25
**Контекст:** B7.10 (presence_signal) + Wave 3 (Layer 2 bulk-roll)
**Master HEAD при создании:** `c531959`

**Как использовать:** см. раздел «Как работать с этим промтом». Кратко: копировать в новый диалог надо ТОЛЬКО блок начиная со второго `# Задача:` (после разделителя `---`).

---

## Как работать с этим промтом

1. Открыть новый диалог с нейросетью.
2. Скопировать **только сам промт** (начиная со второго `# Задача:` после разделителя `---`) в первое сообщение.
3. Нейросеть прочитает контекст, соберёт scope, выведет план и сделает пилотный батч (5-6 checks).
4. Показать результаты юристу.
5. Юрист заполняет раздел «ВЕРДИКТ ЮРИСТА» в каждом блоке (CONFIRM/REJECT/CORRECT).
6. Вернуться в диалог с фидбеком, нейросеть корректирует и переходит к следующему батчу.
7. После всех 86 checks — PR'ы с правками YAML по валидированной таблице решений.

**Не начинать правки в YAML до валидации юристом.**

---

# Задача: Унифицированный анализ checks для юридической валидации

## Твоя роль

Ты — аналитик-инженер-юрист на проекте Steloom. Твоя задача — **подготовить предварительный анализ каждого check'а** в плейбуке, чтобы **юрист-эксперт** мог подтвердить, отклонить или скорректировать твоё предложение.

Твой вывод — **не финальная правка YAML**. Твой вывод — **предложение для ревью юристом** по единому стандарту.

**Ключевые принципы:**
- Лучше `[UNCERTAIN]`, чем уверенный неверный вывод.
- **Не менять обязательные поля** (см. Раздел 0).
- **Сохранять структуру** check'а (global vs doc-type).
- Показывать **diff (БЫЛО / СТАЛО)** для каждого изменения.

## Раздел 0. ОБЯЗАТЕЛЬНЫЕ ПОЛЯ — НЕ ТРОГАТЬ

Код читает эти поля. Их изменение может сломать pipeline. **AI НЕ МЕНЯЕТ их без явного запроса юриста.**

### Структурные (никогда)

- `id`, `name`, `description`
- `doc_types` (может быть `[]` для global или список для doc-type)
- `origin` (`GLOBAL_PLAYBOOK` / `DOCUMENT_TYPE` — определяет место check'а)
- `group` (опционально — UX-группировка)
- `severity`, `severity_if_pass`, `severity_if_fail`, `severity_if_unclear`
- `detector_type`, `ui_mode`
- `triggers` (для doc-type)
- `conditional`
- `store_payload`

### Retrieval (никогда)

Вся секция `retrieval:`:
- `retrieval_profile`, `retrieval_query`
- `boost_keywords`, `negative_keywords`
- `preferred_unit_types`, `excluded_unit_types`, `preferred_clause_functions`
- `position_bias`, `rerank`, `filters`
- `corpus_scope`, `levels`, `required_kind`, `context_k`, `max_chunks`

### Rules (никогда не менять структуру)

- `rules.keyword_mode`
- `rules.keywords` — **структура сохраняется как есть** (nested dict vs flat list)
- `rules.regex_patterns`, `rules.clause_patterns`

### Enrichment / Evidence (никогда)

- `enrichment_hints.*`
- `evidence.*`

### LLM Layer 1 (никогда без явного запроса)

- `llm.prompt_file` (для global) — ссылка на файл
- `llm.prompt_template` (для doc-type) — inline Layer 1
- `llm.context_k`, `llm.temperature`, `llm.max_tokens`

### Extraction — часть полей не трогается

- `extraction.enabled`, `extraction.mode`, `extraction.compact_output`
- `extraction.fields[*].type`, `name`, `presentation`, `display_in_grid`, `display_priority`, `label`, `description`, `required`

## Раздел 1. Поля, которые AI МОЖЕТ добавлять/менять

### Может добавлять

- `extraction.presence_signal` — **только если юрист подтвердит задачу A**.
- `extraction.fields[*].risk_weight` — **только для полей с `presentation: "signal"`** (задача B).
- `<location_instructions>` в `extraction.llm_prompt_extraction` — если отсутствует.
- `<output_expectations>` в `extraction.llm_prompt_extraction` — если отсутствует.
- Few-shot примеры в `extraction.llm_prompt_extraction`.
- `extraction.llm_max_tokens` — **только если** новый prompt не влезает в старый лимит.

### Может менять (с оговорками)

- `extraction.llm_prompt_extraction` — Layer 2 prompt (переработка).
- `extraction.fields[*].allowed_values` — **только если** контракт `presence_signal` требует (union = allowed_values).

## Раздел 2. Различия global vs doc-type — сохранять структуру

| Аспект | Global (`playbooks/global_checks/*`) | Doc-type (`playbooks/document_types/*`) |
|---|---|---|
| `origin` | отсутствует (default) или `GLOBAL_PLAYBOOK` | `DOCUMENT_TYPE` |
| `doc_types` | `[]` | список `[contract_..., ...]` |
| `triggers` | обычно отсутствует | `triggers: {}` или другой |
| `rules.keywords` | nested `{high: [], medium: [], low: []}` | flat list `[...]` |
| Layer 1 prompt | `llm.prompt_file` (ссылка) | `llm.prompt_template` (inline) |
| `presence_signal` | может быть | обычно нет (задача A) |
| `risk_weight` на signal | может быть | обычно нет (задача B) |

**Никогда:**
- Не превращать flat `keywords` в nested dict (или наоборот).
- Не превращать `llm.prompt_file` в `llm.prompt_template` (или наоборот).
- Не добавлять `origin` туда, где его не было.
- Не убирать `triggers`.

## Раздел 3. Две задачи

### Задача A: B7.10 — `presence_signal`

**Проблема.** Для 86 из 87 field_extraction checks система показывает «No issues detected», когда пункта нет. Семантически неверно — «пункт не найден» ≠ «нет риска».

**Решение.** Для каждого check'а решить: обязателен ли пункт?
- Обязателен → добавить `presence_signal` в `extraction:`.
- Опционален → оставить как есть.

**Формат:**
extraction:
presence_signal:
field: <signal_field_name>
present_values: [...]
missing_values: [...]
unclear_values: [...]

text

**Контракт:**
- `field` объявлен в `extraction.fields`.
- Три группы попарно disjoint.
- Union всех трёх = `allowed_values(field)`.

### Задача B: Wave 3 — Layer 2 bulk-roll

1. **`risk_weight`** — добавить в `extraction.fields[*]` для полей с `presentation: "signal"`. Значения enum: `high / medium / low / info`.

2. **Layer 2 prompt** (`extraction.llm_prompt_extraction`) — должен содержать:
   - `<location_instructions>` — что LLM возвращает в `location` (`clause_ref`, `page`, `quote`).
   - `<output_expectations>` — контракт JSON-ответа.
   - Few-shot примеры.

## Раздел 4. Унификация DD Grid output

Независимо от origin (global / doc-type) — **юрист видит одинаково:**

| Что видно в DD Grid | Одинаково для всех checks |
|---|---|
| Result при наличии пункта | `pass` / `fail` |
| Result при отсутствии (обязателен) | `missing_required_clause` |
| Result при отсутствии (опционален) | `pass` |
| `CellRiskBadge` | Показывается при наличии `risk_weight` |
| LOCATION | `p. X · main_contract:Y` |
| `display_text` | Единый формат |

**Твоя задача — обеспечить идентичный контракт. Различие global vs doc-type — только в scope применения.**

### Нюанс: разная обязательность для разных doc-types

Если check применим к нескольким doc-types, и пункт **обязателен для одного, опционален для другого** — пометь `[NEEDS_JURIST_DECISION]` и предложи:
- **Вариант 1:** принять по наиболее строгому doc-type (fail-safe).
- **Вариант 2:** принять по наиболее частому (практично).
- **Вариант 3:** развести на два check'а (ломает унификацию).

Решение — за юристом.

## Раздел 5. Что нужно сделать

### Шаг 1. Прочитай контекст
cd /srv/steloom-dev
head -200 docs/HANDOVER_v7.3.md

text

Раздел 0 (принципы), Раздел 2 (закрытые задачи), Раздел 3 (отменённые гипотезы), Раздел 4 (backlog).

### Шаг 2. Прочитай два эталона
Эталон global check (все три задачи закрыты)
cat playbooks/global_checks/coc/coc_change_of_control_regime.yaml

Эталон doc-type check (задачи A и B ещё не сделаны)
grep -A 200 "parties_and_authority" playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml

text

Первый — образец правильного оформления. Второй — что надо добавить.

### Шаг 3. Собери список checks в scope
grep -rln "ui_mode.field_extraction" playbooks/ | sort > /tmp/b710_checks.txt
wc -l /tmp/b710_checks.txt
grep -rln "risk_weight" playbooks/ | sort
grep -rln "presentation.signal" playbooks/ | sort

text

### Шаг 4. Анализ батчами по 5-6 checks

Первый батч — пилотный, юрист калибрует. Дальше по образцу.

## Раздел 6. Формат вывода

Для каждого check — блок по структуре:
Анализ: <check_id>
Файл: <path>
Origin: GLOBAL_PLAYBOOK / DOCUMENT_TYPE
Doc types: [список]
UI mode: field_extraction

1. Что проверяет check
<1-2 предложения>

2. Текущее состояние
Аспект	Статус
presence_signal	❌/✅/⚠
risk_weight (signal)	❌/✅/⚠
Layer 2 prompt (location_instructions)	❌/✅
Layer 2 prompt (output_expectations)	❌/✅
Структура rules.keywords	nested / flat
Layer 1 prompt	prompt_file / prompt_template
3. Анализ: обязателен ли пункт?
Для каких doc-types обязателен: [...]
Для каких опционален: [...]
Обоснование: <норма / специфика>
Уверенность: 🟢/🟡/🔴
Флаг: [NEEDS_JURIST_DECISION] — если применимо

4. Предлагаемые изменения
Изменение 1: добавить presence_signal
БЫЛО:

text
extraction:
  enabled: true
  mode: "hybrid"
СТАЛО:

text
extraction:
  enabled: true
  mode: "hybrid"
  presence_signal:
    field: <field_name>
    present_values: [...]
    missing_values: [...]
    unclear_values: [...]
ОБОСНОВАНИЕ: <почему>

УВЕРЕННОСТЬ: 🟢/🟡/🔴 [UNCERTAIN]

Проверка контракта:

field в fields: ✅/❌

Попарно disjoint: ✅/❌

Union = allowed_values: ✅/❌

Изменение 2: добавить risk_weight
(аналогично — БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ)

Изменение 3: переработать Layer 2 prompt
(БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ)

Изменение 4: добавить location_instructions / output_expectations
(если отсутствуют)

5. Дополнительные находки (вне двух задач)
Если YAML имеет проблемы, не связанные с задачами A/B — фиксируй с пометкой [CONSIDER / DEFER / IGNORE].

6. ЧЕК-ЛИСТ СОХРАНЕНИЯ ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ
□ Все структурные поля без изменений (id, name, description, doc_types, origin, group, severity*, detector_type, ui_mode, triggers, conditional, store_payload)
□ retrieval.* без изменений
□ rules.keyword_mode, rules.keywords структура — та же
□ rules.regex_patterns, rules.clause_patterns без изменений
□ enrichment_hints., evidence. без изменений
□ llm.prompt_file или llm.prompt_template — те же (Layer 1 не тронут)
□ llm.context_k, temperature, max_tokens — без изменений
□ extraction.enabled, mode, compact_output — без изменений
□ extraction.fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required — без изменений
7. Финальный YAML (для копипасты после апрува)
text
<полный YAML с изменениями>
8. ВЕРДИКТ ЮРИСТА
Изменение 1 (presence_signal)
□ CONFIRM / [ ] REJECT / [ ] CORRECT → ________
Изменение 2 (risk_weight)
□ CONFIRM / [ ] REJECT / [ ] CORRECT → ________
Изменение 3 (Layer 2 prompt)
□ CONFIRM / [ ] REJECT / [ ] CORRECT → ________
Изменение 4 (location/output expectations)
□ CONFIRM / [ ] REJECT / [ ] CORRECT → ________
Дополнительные находки
□ APPLY NOW / [ ] DEFER / [ ] IGNORE
Общий комментарий юриста
text

## Раздел 7. Требования к качеству

### Обязательно

1. Структурные решения, не костыли.
2. Ссылки на нормы ГК / ФЗ / специфику doc-type.
3. `[UNCERTAIN]` — если не уверен.
4. Проверка контракта `presence_signal` — union = allowed_values.
5. Не выдумывать нормы.
6. Один check — один блок.
7. Diff (БЫЛО / СТАЛО) для каждого изменения.
8. Дополнительные находки вне задач A/B.
9. Унификация global vs doc-type.
10. **Не трогать обязательные поля** (Раздел 0).
11. **Сохранять структуру global vs doc-type** (Раздел 2).

### Запрещено

1. ❌ Менять обязательные поля без явного запроса.
2. ❌ Менять `rules.keywords` структуру (nested ↔ flat).
3. ❌ Менять `llm.prompt_file` ↔ `llm.prompt_template`.
4. ❌ Добавлять `origin` там, где его не было.
5. ❌ Менять `retrieval.*`.
6. ❌ Придумывать `risk_weight` без обоснования.
7. ❌ Менять контракт `presence_signal`.
8. ❌ Игнорировать `presentation: "signal"` при добавлении `risk_weight`.
9. ❌ Применять правки без ревью юриста.
10. ❌ `[UNCERTAIN]` с догадкой — если не знаешь, не гадай.

## Раздел 8. Рабочий процесс

1. **Итерация 1 (пилот):** 5-6 checks разной сложности. Юрист валидирует.
2. **Итерация 2-12:** 5-6 checks по категориям.
3. **Финальный результат:** таблица решений для всех 86 checks.

**Не переходить к следующему батчу без фидбека юриста.**

## Команды для старта
cd /srv/steloom-dev
source .venv/bin/activate
export PYTHONPATH=src:.

1. Handover
head -200 docs/HANDOVER_v7.3.md

2. Эталоны
cat playbooks/global_checks/coc/coc_change_of_control_regime.yaml
grep -A 200 "parties_and_authority" playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml

3. Scope
grep -rln "ui_mode.*field_extraction" playbooks/ | sort > /tmp/b710_checks.txt
wc -l /tmp/b710_checks.txt
cat /tmp/b710_checks.txt

4. Модели
sed -n '/class ExtractionConfig/,/^class /p' src/engine/playbook/models.py | head -80
sed -n '/class ExtractionFieldConfig/,/^class /p' src/engine/playbook/models.py | head -60
sed -n '/class PresenceSignalConfig/,/^class /p' src/engine/playbook/models.py | head -40

text

## Первый шаг

1. Прочитай handover + два эталона.
2. Собери список checks в scope.
3. Выведи план: разбивка на батчи, что берёшь в пилотный.
4. Сделай Батч 1 — 5-6 checks по формату выше.
5. Стоп, жди фидбека юриста.

**Не начинай правки в YAML до валидации юристом.**
