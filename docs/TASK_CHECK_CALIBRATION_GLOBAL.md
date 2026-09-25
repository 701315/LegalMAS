# Задача: Унифицированный анализ GLOBAL checks для юридической валидации

**Область:** ТОЛЬКО playbooks/global_checks/*
**Создано:** 2026-09-25
**Контекст:** B7.10 (presence_signal) + Wave 3 (Layer 2 bulk-roll)
**Master HEAD:** c531959
**В scope:** 44 global field_extraction checks (CoC уже готов как эталон)

## Как работать с этим файлом

1. Открыть НОВЫЙ диалог с нейросетью.
2. Скопировать содержимое этого файла целиком в первое сообщение.
3. Нейросеть прочитает контекст, соберёт список 44 global checks, выведет план батчей.
4. Нейросеть делает Батч 1 (5-6 global checks).
5. Показать юристу.
6. Юрист CONFIRM/REJECT/CORRECT по каждому изменению.
7. Возврат в диалог с фидбеком → следующий батч.
8. После всех 44 checks — PR'ы с правками YAML.

**Не начинать правки YAML до валидации юристом.**

---

## ПРАВИЛО ИЗОЛЯЦИИ — читать первым

⚠️ Ты работаешь ТОЛЬКО с checks из playbooks/global_checks/*.

- Никогда не бери в работу checks из playbooks/document_types/*.
- Никогда не смешивай global и doc-type checks в одном батче.
- Если по ошибке взял check не из своей области — останови работу и сообщи пользователю.
- Отдельный промт существует для playbooks/document_types/* — это НЕ он.

## Твоя роль

Ты — аналитик-инженер-юрист на проекте Steloom. Готовишь предварительный анализ GLOBAL checks, чтобы юрист-эксперт подтвердил/отклонил/скорректировал твоё предложение.

Твой вывод — не финальная правка YAML, а предложение для ревью юристом по единому стандарту.

**Ключевые принципы:**
- Лучше [UNCERTAIN], чем уверенный неверный вывод.
- Не менять обязательные поля (см. Раздел 0).
- Показывать diff (БЫЛО / СТАЛО) для каждого изменения.

## ЭТАЛОН — единственный готовый global check

playbooks/global_checks/coc/coc_change_of_control_regime.yaml — 100% оформлен:
- presence_signal ✅
- risk_weight для signal-полей ✅
- Layer 2 custom prompt ✅

Все твои предложения для остальных 44 checks — соответствуют этому стилю.

## Специфика GLOBAL checks (отличается от doc-type!)

- rules.keywords: nested структура high/medium/low. Например:

  rules:
    keyword_mode: any
    keywords:
      high:
        - "(?i)change\\s+of\\s+control"
      medium:
        - "(?i)beneficial\\s+ownership"
      low:
        - "(?i)смена\\s+владельца"

- Layer 1 prompt: llm.prompt_file: "detection/generic_presence.txt" (ссылка на общий файл).
- origin: ОТСУТСТВУЕТ (default = GLOBAL_PLAYBOOK).
- triggers: ОТСУТСТВУЕТ.
- doc_types: [] (пустой список).

⚠️ НЕ меняй эти четыре структурные особенности. Если увидишь отклонение в каком-то global check — это anomaly, фиксируй в дополнительных находках, не «исправляй» автоматически.

## Раздел 0. ОБЯЗАТЕЛЬНЫЕ ПОЛЯ — НЕ ТРОГАТЬ

Код читает эти поля. Их изменение может сломать pipeline.

- Структурные: id, name, description, doc_types, group, severity, severity_if_pass, severity_if_fail, severity_if_unclear, detector_type, ui_mode, conditional, store_payload
- Retrieval (вся секция): retrieval_profile, retrieval_query, boost_keywords, negative_keywords, preferred_unit_types, excluded_unit_types, preferred_clause_functions, position_bias, rerank, filters, corpus_scope, levels, required_kind, context_k, max_chunks
- Rules (никогда не менять структуру): keyword_mode, структура keywords (nested остаётся nested), regex_patterns, clause_patterns
- Enrichment / Evidence: enrichment_hints.*, evidence.*
- LLM Layer 1: prompt_file, context_k, temperature, max_tokens
- Extraction — часть полей: enabled, mode, compact_output, fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required

## Раздел 1. Поля, которые AI МОЖЕТ добавлять/менять

### Может добавлять

- extraction.presence_signal — только если юрист подтвердит (задача A).
- extraction.fields[*].risk_weight — только для полей с presentation: "signal" (задача B).
- <location_instructions> в extraction.llm_prompt_extraction — если отсутствует.
- <output_expectations> в extraction.llm_prompt_extraction — если отсутствует.
- Few-shot примеры в extraction.llm_prompt_extraction.
- extraction.llm_max_tokens — только если новый prompt не влезает в старый лимит.

### Может менять (с оговорками)

- extraction.llm_prompt_extraction — Layer 2 prompt.
- extraction.fields[*].allowed_values — только если контракт presence_signal требует (union = allowed_values).

## Раздел 2. Две задачи

### Задача A: B7.10 — presence_signal

Проблема. Для 44 global field_extraction checks система показывает «No issues detected», когда пункта в договоре нет. Семантически неверно — «пункт не найден» ≠ «нет риска».

Решение. Для каждого check'а решить: обязателен ли пункт?
- Обязателен → добавить presence_signal в extraction:
- Опционален → оставить как есть.

Формат presence_signal (эталон — CoC):

  extraction:
    presence_signal:
      field: <signal_field_name>
      present_values: [...]
      missing_values: [...]
      unclear_values: [...]

Контракт:
- field объявлен в extraction.fields.
- Три группы попарно disjoint.
- Union всех трёх = allowed_values(field).

### Задача B: Wave 3 — Layer 2 bulk-roll

1. risk_weight — добавить в extraction.fields[*] для полей с presentation: "signal". Значения: high / medium / low / info.
2. Layer 2 prompt (extraction.llm_prompt_extraction) — должен содержать:
   - <location_instructions> — что LLM возвращает в location (clause_ref, page, quote).
   - <output_expectations> — контракт JSON-ответа.
   - Few-shot примеры.

## Раздел 3. Что нужно сделать

### Шаг 1. Прочитай контекст

  cd /srv/steloom-dev
  head -200 docs/HANDOVER_v7.3.md

### Шаг 2. Прочитай эталон

  cat playbooks/global_checks/coc/coc_change_of_control_regime.yaml

### Шаг 3. Собери список 44 global checks в scope

  grep -rln "ui_mode.*field_extraction" playbooks/global_checks/ | sort

Ожидается 45 файлов, из них 1 — CoC (эталон, не трогаем). В scope: 44.

### Шаг 4. Анализ батчами по 5-6 checks

Первый батч — пилотный (4-5 checks разной сложности). Юрист калибрует.

## Раздел 4. Формат вывода — для каждого check

# Анализ: <check_id>

Файл: <path>
Origin: GLOBAL_PLAYBOOK
UI mode: field_extraction

## 1. Что проверяет check

<1-2 предложения>

## 2. Текущее состояние

- presence_signal: есть / нет / частично
- risk_weight (signal): есть / нет / частично
- Layer 2 prompt (location_instructions): есть / нет
- Layer 2 prompt (output_expectations): есть / нет

## 3. Анализ: обязателен ли пункт?

Для каких типов договоров обязателен: [...]
Для каких опционален: [...]
Обоснование: <норма ГК / специфика>
Уверенность: высокая / средняя / низкая
Флаг: [NEEDS_JURIST_DECISION] — если разная обязательность

## 4. Предлагаемые изменения

### Изменение 1: добавить presence_signal

БЫЛО:
  extraction:
    enabled: true
    mode: "hybrid"

СТАЛО:
  extraction:
    enabled: true
    mode: "hybrid"
    presence_signal:
      field: <field_name>
      present_values: [...]
      missing_values: [...]
      unclear_values: [...]

ОБОСНОВАНИЕ: <почему>

УВЕРЕННОСТЬ: высокая / средняя / низкая [UNCERTAIN]

ПРОВЕРКА КОНТРАКТА:
- field объявлен в fields: да/нет
- Попарно disjoint: да/нет
- Union = allowed_values: да/нет

### Изменение 2: добавить risk_weight

(аналогично — БЫЛО / СТАЛО / ОБОСНОВАНИЕ / УВЕРЕННОСТЬ)

### Изменение 3: переработать Layer 2 prompt

(если требуется)

### Изменение 4: добавить location_instructions / output_expectations

(если отсутствуют)

## 5. Дополнительные находки (вне задач A/B)

Проблемы YAML, не связанные с задачами — с пометкой [CONSIDER / DEFER / IGNORE].

## 6. ЧЕК-ЛИСТ СОХРАНЕНИЯ ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ

- [ ] Структурные поля без изменений
- [ ] retrieval.* без изменений
- [ ] rules.keyword_mode, структура keywords (nested остаётся nested)
- [ ] rules.regex_patterns, clause_patterns без изменений
- [ ] enrichment_hints.*, evidence.* без изменений
- [ ] llm.prompt_file (Layer 1) без изменений
- [ ] llm.context_k, temperature, max_tokens без изменений
- [ ] extraction.enabled, mode, compact_output без изменений
- [ ] extraction.fields[*].type, name, presentation, display_in_grid, display_priority, label, description, required без изменений

## 7. Финальный YAML (для копипасты после апрува)

<полный YAML с изменениями>

## 8. ВЕРДИКТ ЮРИСТА

### Изменение 1 (presence_signal)
- [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ________

### Изменение 2 (risk_weight)
- [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ________

### Изменение 3 (Layer 2 prompt)
- [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ________

### Изменение 4 (location/output expectations)
- [ ] CONFIRM / [ ] REJECT / [ ] CORRECT → ________

### Дополнительные находки
- [ ] APPLY NOW / [ ] DEFER / [ ] IGNORE

### Общий комментарий юриста
_______________________________________________________________

## Раздел 5. Требования к качеству

### Обязательно

1. Структурные решения, не костыли.
2. Ссылки на нормы ГК / ФЗ / специфику doc-type.
3. [UNCERTAIN] — если не уверен.
4. Проверка контракта presence_signal — union = allowed_values.
5. Один check — один блок.
6. Diff (БЫЛО / СТАЛО) для каждого изменения.
7. Дополнительные находки вне задач A/B.
8. Не трогать обязательные поля (Раздел 0).
9. Работать ТОЛЬКО с global_checks.

### Запрещено

1. Менять обязательные поля без явного запроса.
2. Менять структуру rules.keywords (nested ↔ flat).
3. Менять llm.prompt_file ↔ llm.prompt_template.
4. Добавлять origin или triggers туда, где их не было.
5. Менять retrieval.*.
6. Придумывать risk_weight без обоснования.
7. Менять контракт presence_signal.
8. Игнорировать presentation: "signal" при добавлении risk_weight.
9. Применять правки без ревью юриста.
10. [UNCERTAIN] с догадкой — если не знаешь, не гадай.
11. Брать checks из playbooks/document_types/*.

## Раздел 6. Рабочий процесс

1. Итерация 1 (пилот): 4-5 global checks. Юрист валидирует.
2. Итерация 2-10: по 5-6 global checks.
3. Финальный результат: таблица решений для всех 44 global checks.

Не переходить к следующему батчу без фидбека юриста.

## Команды для старта

  cd /srv/steloom-dev
  source .venv/bin/activate
  export PYTHONPATH=src:.

  # 1. Handover
  head -200 docs/HANDOVER_v7.3.md

  # 2. Эталон
  cat playbooks/global_checks/coc/coc_change_of_control_regime.yaml

  # 3. Scope
  grep -rln "ui_mode.*field_extraction" playbooks/global_checks/ | sort > /tmp/global_checks.txt
  wc -l /tmp/global_checks.txt

## Первый шаг

1. Прочитай handover + эталон CoC.
2. Собери список 44 global checks.
3. Выведи план разбивки на батчи.
4. Сделай Батч 1 — 4-5 global checks по формату Раздела 4.
5. Стоп, жди фидбека юриста.

Не начинай правки в YAML до валидации юристом.
