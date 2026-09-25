# GLOBAL CHECKS — Gap Analysis & Backlog

**Создан:** 2026-09-25
**Контекст:** Wave 3 (Layer 2 bulk-roll) + B7.10 (presence_signal)
**Master HEAD:** c531959
**Область:** playbooks/global_checks/*
**Назначение:** фиксация пробелов в покрытии рисков по группам global checks
для последующей доработки (не входит в Wave 3)

---

## Как читать этот файл

- **Gaps (пробелы)** — риски, применимые к любому типу договора, которые
  НЕ покрыты существующими checks в группе.
- **Cross-references** — риски, покрытые в других группах (не дублируем).
- **Вне scope** — doc-type-specific риски, не для global.
- **P1/P2/P3** — приоритет добавления.

Формат блока для каждой группы — унифицирован (см. скелет в конце файла).

---

## Сводная таблица (заполняется по мере анализа)

| Группа                | Checks        | Покрытие  | P1 gaps   | P2 gaps | P3 gaps | Статус |
|---                    |---            |---        |---        |---    |---|---|
| assignment_transfer   | 3             | ~70%      | 3         | 2 | 2 | ✅ проанализирована |
| coc                   | 4 (1 эталон)  | ~90%      | 2         | 3 | 4 | ✅ проанализирована |
| confidentiality       | 2             | ~35%      | 4         | 4 | 2 | ✅ проанализирована |
| cyber                 | 2             | ~65%      | 2         | 3 | 2 | ✅ проанализирована |
| disputes              | 2             | ~75%      | 2         | 3 | 2 | ✅ проанализирована |
| finance               | 4             | ~75%      | 2         | 4 | 5 | ✅ проанализирована |
| formal                | 4             | ~65%      | 4         | 4 | 5 | ✅ проанализирована |
| hr                    | 2             | ~55%      | 4         | 5 | 4 | ✅ проанализирована |
| ip_it                 | 4             | ~55%      | 4         | 5 | 6 | ✅ проанализирована |
| liability             | 4             | ~55%      | 5         | 6 | 5 | ✅ проанализирована |
| regulatory            | 3             | ~55%      | 4         | 5 | 7 | ✅ проанализирована |
| rw                    | 4             | ~60%      | 6         | 10 | 10 | ✅ проанализирована |
| sanctions             | 3             | ~50%      | 8         | 10 | 6 | ✅ проанализирована |
| term                  | 4             | ~60%      | 8         | 11 | 8 | ✅ проанализирована |

---

## Группа: assignment_transfer

**Директория:** `playbooks/global_checks/assignment_transfer/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 3 из 3
**Статус группы:** покрытие ~70% (ядро полное, 7 пробелов)

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `assignment_transfer_regime` | Базовый режим (prohibited / consent_required / freely_permitted / mixed); покрытие (assignment_only / transfer_only / both) |
| 2 | `assignment_transfer_consent` | Механика согласия: форма (prior_written / written / any_form); срок ответа; deemed consent; стандарт отказа (sole_discretion / not_unreasonably_withheld) |
| 3 | `assignment_transfer_consequences` | Последствия нарушения: право расторжения; механизм (optional / automatic / with_cure); акселерация; изменение цены/условий; cure/waiver |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Асимметрия между сторонами** — «мы уступаем свободно» ≠ «нам уступают свободно». `regime` явно исключает этот вопрос. | ст. 388, 391 ГК РФ; логика баланса интересов | Новое поле `assignment_transfer_symmetry` в `regime` **или** отдельный check |
| G2 | **Carve-outs / permitted transfers** — разрешённые передачи (аффилированные лица, реорганизация, банк-кредитор). Критично для планирования exit. | ст. 388, 392.2 ГК РФ; договорная практика | Новый check `assignment_transfer_carveouts` |
| G3 | **Форма уступки** — уступка должна быть в той же форме, что и основная сделка. Несоблюдение → недействительность. | **ст. 389 ГК РФ** | Новое поле `at_assignment_form` в `consent` **или** отдельный check |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G4 | **Successors and assigns (binding effect)** — boilerplate-оговорка «binding upon and inure to the benefit of the parties and their respective successors and permitted assigns». | ст. 382, 392.2, 392.3 ГК РФ | Новое поле `successors_and_assigns_present` в `regime` |
| G5 | **Уведомление должника** — без письменного уведомления новый кредитор несёт риск; должник вправе не исполнять без доказательств перехода. | **ст. 382 п. 3, ст. 385 ГК РФ** | Новое поле `notice_to_debtor_required` в `consent` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G6 | **Кто даёт согласие / кому** — важно для отсечения конкурентов / related parties. `consent` явно исключает. | ст. 391 п. 1 ГК РФ | Новое поле `consent_from_party` в `consent` |
| G7 | **Возражения должника / set-off** — должник вправе выдвигать против нового кредитора возражения, которые имел против первоначального. | **ст. 386, 412 ГК РФ** | DEFER — узко |

#### Дополнительно (низкий / вне scope)

| ID | Риск | Что нужно |
|---|---|---|
| G8 | Недействительность уступки при нарушении режима (void / voidable) | Поле в `consequences`; ст. 388 п. 3 ГК РФ |
| G9 | Security assignment / залог прав | Doc-type-specific (finance) — не в global |
| G10 | Индексация / пересчёт обязательств при передаче | Поле в `consequences`; для мультивалютных |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Change of Control (CoC) | `coc_*` (4 checks) ✅ |
| Последствия CoC | `coc_consequences` ✅ |
| Ответственность / убытки за нарушение | `liability/*` ✅ |
| Общие основания расторжения | `term/termination_grounds` — частично ✅ |

### 4. Вне scope global

- Security assignment (finance)
- Factoring (finance)
- Секьюритизация (finance)
- Регистрация уступки в реестрах (IP, недвижимость)
- Ограничения для лицензируемых видов деятельности (regulatory)

### 5. Структурные проблемы группы

**Дисбаланс именования полей** — три check'а используют разные префиксы:

| Check | Стиль префикса |
|---|---|
| `assignment_transfer_regime` | `assignment_transfer_*` |
| `assignment_transfer_consent` | `at_consent_*` |
| `assignment_transfer_consequences` | `at_consequences_*` |

Рекомендация: привести к единому стилю в будущем (breaking change, не в Wave 3).

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| P1 | G1 — асимметрия между сторонами | Поле в `regime` или новый check |
| P1 | G2 — carve-outs / permitted transfers | Новый check `assignment_transfer_carveouts` |
| P1 | G3 — форма уступки | Поле в `consent` или новый check |
| P2 | G4 — successors & assigns | Поле в `regime` |
| P2 | G5 — уведомление должника | Поле в `consent` |
| P3 | G6 — кто даёт согласие | Поле в `consent` |
| P3 | G7 — возражения должника | DEFER |

**Минимум для полноты группы:** 3 новых check'а (carveouts, форма, возможно асимметрия) + 2–3 новых поля в существующих.

---


## Группа: coc

**Директория:** `playbooks/global_checks/coc/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4 (1 эталон + 3)
**Статус группы:** покрытие ~90% (одна из самых зрелых групп)

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `coc_change_of_control_regime` | Базовый режим CoC (prohibited / consent_required / notice_required / termination_right / mixed). **Эталон 100%** |
| 2 | `coc_consent_terms` | Механика согласия: форма, срок ответа, deemed consent, стандарт отказа |
| 3 | `coc_consequences` | Substantive последствия: право расторжения, механизм, акселерация, изменение цены / условий, cure/waiver |
| 4 | `coc_presence` | Screening: наличие CoC-клаузы; тип триггера (direct / indirect / UBO / broad); пробелы покрытия; routing-сигнал последствий |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Definition of control** — что считается сменой контроля (порог %, voting rights, ability to appoint directors). Без этого режим невозможно применить. | Договорная практика; M&A DD standard | Поле `coc_control_definition` в `coc_presence` |
| G2 | **Carve-outs / permitted CoC** — исключения (внутри группы, аффилированные лица, реорганизация, IPO, банк-кредитор). Первое, что смотрит M&A-юрист при планировании exit. | Договорная практика | Поле `coc_carveouts` в `coc_presence` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Что нужно |
|---|---|---|
| G3 | **Timing / момент срабатывания CoC** — signing / closing / передача / регистрация | Поле `coc_trigger_timing` в `coc_presence` |
| G4 | **Renegotiation right — механика** — кто, когда, что пересматривает | Поле `coc_renegotiation_terms` в `coc_consequences` |
| G5 | **Notice — детали** — срок, форма, кому | Поле `coc_notice_terms` в `coc_consent_terms` |

#### 🟢 P3 — низкий / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G6 | **Waiver / deemed consent для CoC** | Поле в `coc_consequences` |
| G7 | **Асимметрия между сторонами** | Поле в `coc_presence` |
| G8 | **Buy-out / put option при CoC** | DEFER — узко |
| G9 | **CoC vs assignment overlap (обратный)** | DEFER — пограничный случай |

### 3. Cross-references

| Риск | Где покрыто |
|---|---|
| Уступка прав / перевод долга | `assignment_transfer/*` ✅ |
| Ответственность / убытки | `liability/*` ✅ |
| Общие основания расторжения | `term/termination_grounds` — частично ✅ |

### 4. Вне scope global

- Специфика публичных компаний (securities law) — regulatory / doc-type
- Anti-takeover provisions — M&A-specialized
- SPV / project finance — finance / doc-type
- Regulatory change-of-control approvals — regulatory / doc-type

### 5. Структурные проблемы группы

- ✅ Аномалии `coc_presence` (порядок полей) — исправлены в текущем PR
- ⚠️ `coc_change_of_control_regime.coc_status` и `coc_presence.has_coc_clause` семантически дублируются. Pipeline не проверяет согласованность. → DEFER — backlog архитектуры

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — definition of control | Поле `coc_control_definition` в `coc_presence` |
| **P1** | G2 — carve-outs | Поле `coc_carveouts` в `coc_presence` |
| P2 | G3 — timing | Поле `coc_trigger_timing` в `coc_presence` |
| P2 | G4 — renegotiation | Поле `coc_renegotiation_terms` в `coc_consequences` |
| P2 | G5 — notice | Поле `coc_notice_terms` в `coc_consent_terms` |
| P3 | G6–G9 | DEFER |

**Минимум для полноты:** 2 новых поля P1 (`coc_control_definition`, `coc_carveouts`) в `coc_presence`.














## Группа: confidentiality

**Директория:** `playbooks/global_checks/confidentiality/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 2 из 2
**Статус группы:** покрытие ~35% — только screening; детальный режим конфиденциальности и ПДн не разобран

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `confidentiality_and_trade_secrets` | Screening: наличие режима конфиденциальности; срок (contract_specified / perpetual / applicable_law_reference / not_specified) |
| 2 | `personal_data_and_dpa` | Screening: наличие регулирования ПДн; уровень (dpa_attachment / dedicated_section / law_reference_only) |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Definition of confidential information** — что именно защищается, какие категории информации. Description явно исключает из screening-check. | Договорная практика; ст. 1465 ГК РФ (секрет производства) | Новое поле `confidential_information_definition` в `confidentiality_and_trade_secrets` или отдельный check |
| G2 | **Carve-outs / exceptions** — стандартные исключения: public domain, independently developed, received from third party, required by law. Критично для оценки реальной защиты. | Договорная практика | Новый check `confidentiality_exceptions` |
| G3 | **Permitted disclosures** — кому разрешено раскрывать: аффилированные лица, консультанты, аудиторы, DD-консультанты, регуляторы. **Ключевое для M&A-сделок.** | Договорная практика; M&A standard | Новый check `confidentiality_permitted_disclosure` |
| G4 | **Roles in data processing** — controller / processor / joint controller. Без этого DPA-режим невозможно применить. | GDPR Art. 24–28; 152-ФЗ ст. 6 | Новое поле `personal_data_roles` в `personal_data_and_dpa` или отдельный check |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G5 | **Return / destruction of information** — процедура возврата/уничтожения носителей при прекращении. | Договорная практика | Новое поле `confidentiality_return_destruction` |
| G6 | **Marking / identification requirements** — требуется ли маркировать информацию как конфиденциальную. | Договорная практика | Новое поле `confidentiality_marking` |
| G7 | **Cross-border transfer** — трансграничная передача ПДн, SCC, adequacy decisions. | GDPR Chapter V; 152-ФЗ ст. 12 | Новое поле `personal_data_cross_border` |
| G8 | **Data breach notification** — срок, порядок, ответственная сторона. | GDPR Art. 33–34; 152-ФЗ | Новый check `personal_data_breach_notification` |

#### 🟢 P3 — низкий / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G9 | **Surviving obligations** — детали: что именно survives, на какой срок | Поле в `confidentiality_and_trade_secrets` |
| G10 | **Data subject rights** — права субъектов ПДн (access, rectification, erasure, portability) | Поле в `personal_data_and_dpa` |
| G11 | **Subprocessors** — привлечение третьих лиц для обработки | Поле в `personal_data_and_dpa` |
| G12 | **Categories of data / sensitive data** — какие категории ПДн обрабатываются | Поле в `personal_data_and_dpa` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Разглашение при уступке / переводе долга | `assignment_transfer/*` — частично ✅ |
| Разглашение при CoC | `coc_*` — частично ✅ |
| Ответственность за нарушение конфиденциальности | `liability/*` — частично ✅ |

### 4. Вне scope global

- Отраслевые режимы (банковская тайна, врачебная тайна) — doc-type
- State secrets (гостайна) — специальный режим
- Специфика публичных компаний (SEC disclosure) — regulatory / doc-type

### 5. Структурные проблемы группы

- ⚠️ В обоих checks порядок `<context>` → `<context_rules>` (инвертирован против эталона CoC — `<context_rules>` → `<context>`). Не ломает pipeline, но нарушает шаблон. → CONSIDER — унифицировать в отдельном PR.
- ⚠️ `personal_data_and_dpa` использует тот же `retrieval_profile: "confidentiality_check"`, что и `confidentiality_and_trade_secrets`. Возможна неоптимальная retrieval-выдача при смешанных запросах (ПДн vs коммерческая тайна). → CONSIDER — возможно, нужен отдельный `personal_data_check` профиль.
- ⚠️ Description обоих checks обещают «отдельные специализированные checks», которых в группе нет. Группа декларирует будущее расширение, но реализовано только 2 screening-чека.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| P1 | G1 — definition of confidential information | Поле в `confidentiality_and_trade_secrets` |
| P1 | G2 — carve-outs | Новый check `confidentiality_exceptions` |
| P1 | G3 — permitted disclosures | Новый check `confidentiality_permitted_disclosure` |
| P1 | G4 — roles in data processing | Поле в `personal_data_and_dpa` |
| P2 | G5–G8 | Поля + новый check (breach notification) |
| P3 | G9–G12 | DEFER |

**Минимум для полноты группы:** 2 новых check'а P1 (`confidentiality_exceptions`, `confidentiality_permitted_disclosure`) + 2 поля P1 (`confidential_information_definition`, `personal_data_roles`).

**Общая оценка:** группа сильно недоразвита. Покрытие ~35%. Screening + срок + уровень — это уровень «наличие есть / нет». Детальный режим конфиденциальности (исключения, permitted disclosure, marking, return) и ПДн (роли, transfer, breach, субъекты) — отсутствуют.


## Группа: cyber

**Директория:** `playbooks/global_checks/cyber/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 2 из 2
**Статус группы:** покрытие ~65% — два больших screening-чека, детальный разбор отсутствует

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `cybersecurity_policies_and_incidents` | ИБ-контур: политики/сертификации (ISO 27001, SOC 2, PCI DSS), конкретные меры, процедуры реагирования, обязательства уведомления, прошлые инциденты |
| 2 | `outsourced_it_and_security_risk` | ИТ-аутсорсинг: функции, ИБ-обязательства провайдера, контроль субподрядчиков, приостановка сервиса, export/transition, SLA, односторонние изменения |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Data localization / требования о хранении данных на территории РФ** — критично для 152-ФЗ, банковской тайны и гостайны | 152-ФЗ ст. 18 ч. 5; отраслевые нормы | Новое поле `data_localization_requirements` в `personal_data_and_dpa` или отдельный check |
| G2 | **SLA-механика в деталях** — конкретные метрики, как считаются service credits, окна обслуживания, экскалация | Договорная практика | Новое поле в `outsourced_it_and_security_risk`: `sla_mechanics` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Что нужно |
|---|---|---|
| G3 | **Regulatory notifications (ЦБ, РКН, ФСТЭК)** — специфические требования к уведомлению при ИБ-инцидентах | Поле в `cybersecurity_policies_and_incidents` |
| G4 | **Business continuity / DR** — конкретные RTO/RPO, обязательства по восстановлению | Поле в `cybersecurity_policies_and_incidents` |
| G5 | **Cyber insurance** — наличие киберстраховки у провайдера | Поле в `cybersecurity_policies_and_incidents` |

#### 🟢 P3 — низкий / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G6 | **Right to audit** — право клиента на аудит ИБ-практик провайдера | Поле в `outsourced_it_and_security_risk` |
| G7 | **Vendor concentration risk** — сколько критических функций у одного провайдера | Поле в `outsourced_it_and_security_risk` |

### 3. Cross-references

| Риск | Где покрыто |
|---|---|
| ПДн (роли, цели, категории) | `confidentiality/personal_data_and_dpa` — частично ✅ |
| Data breach notification | `personal_data_and_dpa` — частично ✅ |
| Ответственность за ИБ-инциденты | `liability/*` — частично ✅ |

### 4. Вне scope global

- Отраслевые стандарты (PCI DSS для платёжных) — doc-type
- Гостайна — специальный режим
- Публичные компании — SEC disclosure — regulatory / doc-type

### 5. Структурные проблемы группы

- ⚠️ В обоих checks порядок `<context>` → `<context_rules>` (инвертирован против эталона CoC). → CONSIDER — унифицировать в отдельном PR.
- ⚠️ Оба checks используют одинаковый `retrieval_profile: "cybersecurity_check"` с разными `context_k` (6 vs 7) и `max_chunks` (10 vs 15). → CONSIDER — возможно, нужны отдельные профили.
- ⚠️ В `cybersecurity_policies_and_incidents` отсутствует `technical_specification` в `excluded_segment_types` (в других ИБ-чеках — есть). → CONSIDER.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — data localization | Поле в `personal_data_and_dpa` |
| **P1** | G2 — SLA-механика | Поле в `outsourced_it_and_security_risk` |
| P2 | G3–G5 | Поля |
| P3 | G6–G7 | Поля |

**Минимум для полноты группы:** 2 поля P1 (data localization, SLA-механика). Новых checks не требуется — группа структурно полная, но требует углубления по отдельным аспектам.

**Общая оценка:** группа хорошо покрывает основные сценарии ИБ-контура и ИТ-аутсорсинга. Пробелы — узкие, не универсальные.


## Группа: disputes

**Директория:** `playbooks/global_checks/disputes/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 2 из 2
**Статус группы:** покрытие ~75% — ядро разрешения споров покрыто, детали арбитража и parallel proceedings — нет

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `governing_law_and_forum` | Применимое право + форум разрешения споров + routing-сигнал наличия досудебной процедуры |
| 2 | `limitation_periods_and_pre_claim_procedures` | Обязательность досудебного порядка; срок предъявления требования / иска; момент начала течения |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Детали арбитражной процедуры** — seat, язык, количество арбитров, interim measures, назначение арбитров, порядок формирования трибунала | Регламенты ICC, LCIA, МКАС | Новый check `dispute_resolution_procedure_details` (прямо упоминается в `description`) |
| G2 | **Конфликт оговорок** — несовместимые положения (например, «суды Англии» + «МКАС» в разных пунктах). Сейчас помечается как `unclear`, но **не диагностируется** | Договорная практика | Новое поле `dispute_clause_conflict` в `governing_law_and_forum` или отдельный check |

#### 🟡 P2 — средний приоритет

| ID | Риск | Что нужно |
|---|---|---|
| G3 | **Exclusive vs non-exclusive jurisdiction** — сейчас не фиксируется | Поле `jurisdiction_exclusivity` в `governing_law_and_forum` |
| G4 | **Multi-tier dispute resolution** — эскалация: переговоры → медиация → арбитраж. Детали перехода | Новое поле `dispute_escalation_structure` |
| G5 | **Interim / injunctive relief** — право на обеспечительные меры в обход арбитража | Поле в `dispute_resolution_procedure_details` (future check) |

#### 🟢 P3 — низкий / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G6 | **Anti-suit injunctions / parallel proceedings** | DEFER — узко |
| G7 | **Cost allocation / fee shifting** — кто платит расходы на спор | Поле в детальном check'е |

### 3. Cross-references

| Риск | Где покрыто |
|---|---|
| Ответственность за нарушение | `liability/*` — частично ✅ |
| Расторжение договора | `term/termination_grounds` ✅ |
| Досудебный порядок для уступки/CoC | `assignment_transfer_consent`, `coc_consent_terms` ✅ |

### 4. Вне scope global

- Специфика арбитража ad hoc vs институционального — regulatory / doc-type
- Cross-border enforcement (New York Convention) — regulatory / doc-type
- Медиация по специальным регламентам (Сингапурская конвенция) — doc-type

### 5. Структурные проблемы группы

- ⚠️ Оба checks используют разные `retrieval_profile`: `governing_law_check` vs `dispute_resolution_check`. Консистентно, но проверить оба в БД.
- ⚠️ `description` `governing_law_and_forum` обещает `dispute_resolution_procedure_details` — отдельного check'а нет. Группа декларирует 3 check'а, реализовано 2.
- ⚠️ `<context>` до `<context_rules>` в обоих — унифицировать с остальными группами.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — детали арбитража | Новый check `dispute_resolution_procedure_details` |
| **P1** | G2 — конфликт оговорок | Поле `dispute_clause_conflict` |
| P2 | G3–G5 | Поля |
| P3 | G6–G7 | DEFER |

**Минимум для полноты группы:** 1 новый check P1 (детали арбитража) + 1 поле P1 (конфликт оговорок).

**Общая оценка:** хорошая группа. Ядро (право, форум, давность, претензионный порядок) покрыто полностью. Пробелы — специфические процедурные аспекты, декларированные в description.

## Группа: finance

**Директория:** `playbooks/global_checks/finance/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~75% — ядро финансового DD покрыто, отсутствуют механические аспекты кредитной документации

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `financial_covenants` | Финансовые ковенанты: leverage ratio, DSCR, ICR, liquidity; ограничения на дивиденды и новый долг; тип (maintenance / incurrence); baskets / permitted exceptions; cure / equity cure; cross-default |
| 2 | `payment_terms_and_structures` | Платёжные условия: валюта, структура (advance / post / milestone / mixed / periodic), штрафы за просрочку, предоплаты / аккредитивы / escrow, set-off / netting, индексация цен |
| 3 | `security_and_encumbrances_general` | Обеспечение: залоги / ипотека / гарантии / поручительства; negative pledge; ограничения на отчуждение активов; приоритет (first / second / pari passu); permitted liens; release conditions; upstream / cross-stream |
| 4 | `sticky_long_term_obligations` | Долгосрочные минимальные обязательства: take-or-pay, минимальные объёмы, фиксированные платежи; срок; auto-renewal; survival при CoC; индексация; shortfall penalties; exit fee; renegotiation |

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Определения финансовых терминов** — что считается «Debt», «EBITDA», «Cash», «Permitted Indebtedness». Без определений ковенанты невозможно применить: разные методики расчёта могут полностью изменить картину нарушения | Договорная практика; IFRS / РСБУ | Новое поле `financial_terms_definitions` в `financial_covenants` |
| G2 | **Механика досрочного погашения** — voluntary / mandatory prepayment, notice periods, prepayment fee, break costs. Существенно для планирования exit / рефинансирования | Договорная практика | Новый check `prepayment_mechanics` или поле в `payment_terms_and_structures` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Что нужно |
|---|---|---|
| G3 | **Margin ratchet** — ставка привязана к leverage ratio / рейтингу. Ключевая экономика кредита | Поле `margin_ratchet` в `financial_covenants` |
| G4 | **Mandatory prepayment events** — asset sale proceeds, insurance proceeds, debt issuance, IPO. Связь с `security_and_encumbrances_general` (asset disposal) | Поле `mandatory_prepayment_events` в `payment_terms_and_structures` |
| G5 | **Financial reporting covenants** — периодическая сдача отчётности, compliance certificate, сроки | Поле `financial_reporting_covenants` в `financial_covenants` |
| G6 | **Subordination / intercreditor** — старшинство долга (senior / subordinated / mezzanine), договорные механизмы ранжирования. Упоминается в `security`, но не анализируется | Новое поле `subordination_terms` или отдельный check |

#### 🟢 P3 — низкий / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G7 | **Cash sweep** — обязательное досрочное погашение из свободного денежного потока | Поле в `payment_terms_and_structures` |
| G8 | **Anti-hoarding** — запрет на накопление кэша сверх лимита | Поле в `financial_covenants` |
| G9 | **Equity cure — детали** — кто может, сколько раз, лимит | Расширение поля в `financial_covenants` |
| G10 | **Tax gross-up / illegality / increased costs** — налоговые и регуляторные оговорки в кредитной документации | Поле в `payment_terms_and_structures` |
| G11 | **Benchmark replacement** — механика замены референсной ставки (LIBOR → SOFR / RUONIA) | Поле в `payment_terms_and_structures` |

### 3. Cross-references

| Риск | Где покрыто |
|---|---|
| Уступка прав / перевод долга по кредиту | `assignment_transfer/*` ✅ |
| Смена контроля (CoC) | `coc/*` ✅ |
| Ответственность за нарушение | `liability/*` ✅ |
| Досудебный порядок по финансовым спорам | `disputes/*` ✅ |
| Санкционные ограничения платежей | `sanctions/*` — частично ✅ |

### 4. Вне scope global

- Syndication / loan transfer mechanics — doc-type (credit agreement)
- Export credit agency (ECA) specifics — regulatory / doc-type
- Project finance / SPV structures — finance / doc-type
- Securitization / factoring — finance / doc-type
- Sub-participation — doc-type

### 5. Структурные проблемы группы

- ✅ Отсутствуют (все 4 check'а следуют единому паттерну)
- ⚠️ `severity_if_fail` в `security_and_encumbrances_general` = `critical` при `severity = high`. Уникальный случай — обосновано, задокументировать `as designed`
- ⚠️ `payment_terms_and_structures` использует `retrieval_profile: "payment_terms_check"`, `sticky_long_term_obligations` — тот же профиль. Возможна неоптимальная retrieval при смешанных запросах

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — определения финансовых терминов | Поле в `financial_covenants` |
| **P1** | G2 — prepayment mechanics | Новый check или поле в `payment_terms_and_structures` |
| P2 | G3–G6 | Поля (3) + новый check (subordination) |
| P3 | G7–G11 | Поля |

**Минимум для полноты группы:** 1 поле P1 (`financial_terms_definitions`) + 1 новый check P1 (`prepayment_mechanics`). Дальнейшее — опционально.

**Общая оценка:** группа хорошо покрывает ядро финансового DD (ковенанты, платежи, обеспечение, долгосрочные обязательства). Пробелы — механические аспекты кредитной документации (определения, prepayment, subordination), критичные для крупных кредитных сделок, но не универсальные для всех договоров.



## Группа: formal

**Директория:** `playbooks/global_checks/formal/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~65% — покрыт «ядро» документа (кто подписал, на каком основании, стороны, полнота пакета, корпоративные одобрения), но **отсутствуют формальные аспекты самого документа** (форма, язык, место/дата подписания, counterparts, notices, boilerplate)

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `corporate_approvals_and_transaction_qualification` | Корпоративные одобрения и квалификация: крупная сделка (ст. 46 14-ФЗ / 78–79 208-ФЗ), заинтересованная сделка (ст. 45 14-ФЗ / 81–84 208-ФЗ), решения СД / ОСА, тайминг одобрения (до / после подписания) |
| 2 | `document_completeness_and_side_letters` | Полнота пакета: приложения (schedules / exhibits / appendices), side letters, disclosure schedules, entire agreement clause, amendments и их консолидация, признаки расхождений с реестрами |
| 3 | `party_identification_and_requisites` | Идентификация сторон: наименование, ОПФ, ОГРН / ИНН / КПП, юридический / почтовый адрес, банковские реквизиты; согласованность между преамбулой / реквизитами / подписным блоком |
| 4 | `signatory_authority_and_basis` | Полномочия подписантов: ФИО и должности, основание (устав / доверенность / решение органа), полнота реквизитов доверенности, признаки выхода за пределы полномочий |

**Что это даёт в сумме:** проверяется **«кто»** (parties, signatories), **«на каком основании»** (authority, corporate approvals), **«что приложено»** (completeness, side letters). Проверяется **содержательная формалистика документа**.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Форма сделки** — соответствует ли форма договора требованиям закона: письменная форма для ЮЛ (единый документ или обмен документами), допустимость электронной подписи, соблюдение требований к форме отдельных видов сделок. Нарушение формы → недействительность / незаключённость. | **ст. 160, 162, 434 ГК РФ** | Новое поле `contract_form_type` в `document_completeness_and_side_letters` **или** отдельный check `contract_form_compliance` |
| G2 | **Язык договора и приоритет версии** — критично для российских ЮЛ: обязательность русского языка для ряда договоров (ст. 3 ГК, 152-ФЗ о языках народов РФ), для двуязычных договоров — **какая версия имеет приоритет**, требуется ли заверенный перевод. | **ст. 3 ГК РФ, ФЗ-53 «О языках народов РФ»** | Новое поле `contract_language_and_priority` **или** отдельный check `contract_language` |
| G3 | **Дата и место подписания** — место подписания определяет применимое право при отсутствии оговорки (ст. 1211 ГК РФ), дата критична для определения момента заключения и привязки к корпоративным одобрениям (см. `corporate_approvals`) | **ст. 1211 ГК РФ, ст. 433 ГК РФ** | Новое поле `signing_date_and_place` — важно для cross-reference с `corporate_approvals` (approval_timing) |
| G4 | **Количество экземпляров / counterparts** — сколько оригиналов, имеют ли юридическую силу копии, допустимо ли подписание в counterparts (важно для многосторонних сделок, M&A) | Договорная практика; для отдельных сделок — прямое требование закона | Новое поле `counterparts_clause` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G5 | **Notices / порядок коммуникации** — адреса для уведомлений, способы (email / почта / курьер / ЭДО), правила deemed receipt, уполномоченные получатели. Критично при спорах о расторжении / одобрении / CoC. | Договорная практика; **ст. 165.1 ГК РФ** (юридически значимые сообщения) | Новый check `notices_and_communication` |
| G6 | **Severability** — оговорка о сохранении силы остальных условий при недействительности части. | Договорная практика; **ст. 180 ГК РФ** | Новое поле `severability_clause` в `document_completeness_and_side_letters` |
| G7 | **No waiver / amendment in writing only** — оговорка, что отказ от права не презюмируется, а изменения только письменно. Критично для защиты от неявных модификаций. | Договорная практика | Новое поле `no_waiver_and_written_amendment` в `document_completeness_and_side_letters` |
| G8 | **Электронная подпись (63-ФЗ)** — если подписание ЭП: вид (УКЭП / УНЭП / ПЭП), оператор ЭДО, наличие соглашения сторон. Для ряда сделок требуется именно УКЭП. | **ФЗ-63 «Об электронной подписи»** | Новое поле `electronic_signature_type` в `signatory_authority_and_basis` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G9 | **Печать организации** — обязательна ли печать по договору или уставу (с 2015 — не общая обязанность ЮЛ, но может быть оговорена); корректность оттиска | Поле `seal_present` |
| G10 | **Целостность документа** — прошивка, нумерация страниц, отметки о количестве листов; критично для документов на бумаге, оспаривания подделки | Поле `document_integrity_markers` |
| G11 | **Нотариальное удостоверение / государственная регистрация** — требуется ли нотариальное удостоверение сделки (прямо оговорено законом) или государственная регистрация (недвижимость, ИС, отдельные виды) | DEFER — узко / doc-type-specific |
| G12 | **Effective date vs signing date** — отдельная оговорка о вступлении в силу (после выполнения conditions precedent), условия вступления в силу, retroactive effect | Поле `effective_date_clause` |
| G13 | **Corporate representations** — заявления о надлежащей организации, полномочиях, отсутствии конфликта с уставом / применимым правом; обычно есть в SPA / long-form, но не покрыто | Поле `corporate_reps_present` |

#### Дополнительно (низкий / вне scope)

| ID | Риск | Что нужно |
|---|---|---|
| G14 | Change of name / address of parties after signing (процедура уведомления) | Поле в `party_identification` — связь с notices |
| G15 | Group structure / ownership disclosure (UBO, affiliates) | Частично в `party_identification` и `corporate_approvals`; возможно, отдельно |
| G16 | Specific formal requirements by doc-type (вексель, коносамент и т.п.) | Вне scope global — doc-type |
| G17 | Notarization / apostille for cross-border | Вне scope global — regulatory / doc-type |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Применимое право и форум (в т.ч. как следствие места подписания) | `disputes/governing_law_and_forum` ✅ |
| Уступка прав (форма уступки — G3 в assignment_transfer) | `assignment_transfer/*` ✅ |
| CoC: определение момента срабатывания, definition of control | `coc/*` ✅ |
| Ответственность за нарушение формальных требований | `liability/*` — частично ✅ |
| Вступление в силу (conditions precedent) | `term/*` — частично ✅ |

### 4. Вне scope global

- Отраслевые требования к форме (вексель, коносамент, транспортные накладные)
- Нотариальные и регистрационные процедуры для отдельных видов сделок (недвижимость, ИС, доли в ООО — п. 11 ст. 21 14-ФЗ)
- Cross-border formalization: апостиль, легализация, консульская легализация
- Регистрационные действия в иностранных реестрах
- Специальные требования для публичных компаний (SEC filings)

### 5. Структурные проблемы группы

- ⚠️ **Порядок `<context>` / `<context_rules>`** — во всех 4 checks `<context>` идёт **до** `<context_rules>` (в эталоне CoC — наоборот). Не ломает pipeline, но нарушает шаблон. → CONSIDER — унифицировать в отдельном PR.
- ⚠️ **Дубли в nested `keywords`** — во всех 4 checks есть пересечения regex между уровнями `high` / `medium` / `low` (например, `side letter` — в high и low; `ОГРН` — в high и low; `power of attorney` — в high и low). Структурная anomaly (nested keywords должны быть семантически disjoint). → CONSIDER.
- ⚠️ **`retrieval_profile` — переиспользование** без отдельного «formal» профиля: `corporate_approvals` использует `authority_check`, `signatory` — тоже `authority_check`, `document_completeness` — `definitions_check`, `party_identification` — `authority_check`. Возможна неоптимальная выдача при смешанных запросах. → CONSIDER — возможно, нужен отдельный `formal_check` профиль.
- ⚠️ **`severity_if_fail: critical` при `severity: high`** — в двух checks (`corporate_approvals`, `signatory_authority`). RF8-mismatch. Вероятно, осознанно, но требует документирования как `as designed`. → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** — во всех 4 checks `description` обещает «оценку риска», `<role>` запрещает оценку риска. RF9. → CONSIDER, `description` не меняется.
- ⚠️ **Незакрытые «смежные» темы между checks группы**:
  - `party_identification.party_details_consistent` ↔ `signatory_authority.signatories_identified` — семантически близкие поля, не консистентны между check'ами.
  - `corporate_approvals.approval_timing` ↔ `document_completeness.has_amendments` — тайминг одобрения и дата amendments могут конфликтовать, но pipeline не проверяет.
  - → DEFER — backlog архитектуры.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — форма сделки (ст. 160, 434 ГК РФ) | Новый check `contract_form_compliance` **или** поле `contract_form_type` в `document_completeness` |
| **P1** | G2 — язык договора и приоритет версии | Новый check `contract_language` |
| **P1** | G3 — дата и место подписания | Поле `signing_date_and_place` (cross-ref с `corporate_approvals`) |
| **P1** | G4 — counterparts / количество экземпляров | Поле `counterparts_clause` |
| P2 | G5 — notices / юридически значимые сообщения (ст. 165.1 ГК РФ) | Новый check `notices_and_communication` |
| P2 | G6 — severability (ст. 180 ГК РФ) | Поле в `document_completeness` |
| P2 | G7 — no waiver / amendments in writing | Поле в `document_completeness` |
| P2 | G8 — электронная подпись (63-ФЗ) | Поле в `signatory_authority` |
| P3 | G9–G13 | DEFER — backlog |

**Минимум для полноты группы:**
- 2 новых check'а P1: `contract_form_compliance`, `contract_language`.
- 2 поля P1: `signing_date_and_place`, `counterparts_clause`.
- 1 новый check P2: `notices_and_communication` (важно для cross-reference с `coc`, `assignment_transfer`, `term`).

**Общая оценка:** группа `formal` покрывает **содержательную формалистику** (кто, на каком основании, что приложено), но почти не покрывает **формальные атрибуты самого документа** (форма, язык, место/дата, counterparts, notices, boilerplate). Последние — универсальные для любого договора и критичны в спорных ситуациях, где именно формальные дефекты становятся основанием оспаривания. Рекомендуется **минимум 2 новых check'а + 4–6 новых полей** для доведения группы до ~90% покрытия.


## Группа: hr

**Директория:** `playbooks/global_checks/hr/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 2 из 2
**Статус группы:** покрытие ~55% — покрыты CBA / соцпакет и M&A-механики для топ-менеджмента, но отсутствуют: ПДн работников (специфика), переход сотрудников при asset deal / outsourcing (ТК РФ ст. 75), HR compliance reps, охрана труда, immigration

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `hr_collective_agreements_and_social_packages` | Коллективные договоры (CBA) и соглашения с профсоюзами: наличие и срок CBA, соцпакет (ДМС, доп. отпуск, пенсионная программа), enhanced severance, ограничения на сокращения (no-redundancy, job security, moratorium), обязательные консультации при реорганизации / CoC, сила профсоюза |
| 2 | `hr_key_management_and_change_of_control` | Топ-менеджмент и key employees в M&A: golden parachutes и CoC-выплаты (single / double trigger), severance и exit payments, retention bonuses, good / bad leaver, vesting / acceleration, non-compete / non-solicit |

**Что это даёт в сумме:** проверяются **два ключевых блока HR-рисков в M&A** — (а) коллективные обязательства и социальная нагрузка, (б) индивидуальные M&A-механики для top management. Обе темы — прямое влияние на стоимость сделки и post-closing устойчивость бизнеса.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Обработка ПДн работников (HR-PDn специфика)** — согласия работников, медицинские данные, биометрия, сроки хранения, передача третьим лицам, обработка при реорганизации. Существующий `confidentiality/personal_data_and_dpa` покрывает ПДн в общем, но не HR-специфику (ст. 86–88 ТК РФ, ст. 9 152-ФЗ применительно к работникам). | **ст. 86–88 ТК РФ; ст. 9, 10 152-ФЗ** | Новое поле `employee_data_processing_status` в `personal_data_and_dpa` **или** отдельный check `employee_data_processing` |
| G2 | **Переход сотрудников при asset deal / outsourcing / смене собственника** — сохранение трудовых отношений, уведомления, сроки, компенсации, согласие работников. В РФ нет TUPE-аналога, но есть ст. 75 ТК РФ (смена собственника), ст. 77 ч. 6 ТК РФ (отказ работника), ст. 81 ч. 1 п. 1 (ликвидация / сокращение). | **ст. 75, 77, 81 ТК РФ** | Новый check `employee_transfer_on_deal` |
| G3 | **HR compliance representations** — заявления о соблюдении трудового законодательства: отсутствие забастовок, задолженностей по зарплате, нарушений охраны труда, дискриминации. Критично для M&A reps & warranties. | ТК РФ (разделы III, X); практика M&A | Новое поле `hr_compliance_reps` в `hr_collective_agreements` **или** отдельный check `hr_compliance_representations` |
| G4 | **Key employee non-financial retention** — обязанности сохранения ключевых лиц через: non-disparagement, IP assignment со стороны сотрудников, обязательства сотрудника перед работодателем. Финансовые механизмы (retention bonus) покрыты, нефинансовые — нет. | ст. 1370 ГК РФ (служебные произведения); договорная практика | Новое поле `key_employee_nonfinancial_retention` в `hr_key_management` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G5 | **Охрана труда / Health & Safety** — СОУТ (специальная оценка условий труда), обязательные медосмотры, инструктажи, несчастные случаи, отчётность. Для промышленных сделок — критично. | **426-ФЗ о СОУТ; X раздел ТК РФ** | Новое поле `health_safety_obligations` в `hr_collective_agreements` |
| G6 | **Immigration / work permits** — иностранные сотрудники: разрешения на работу, визы, патенты, регистрация. Для международных сделок и IT-компаний с распределённой командой. | **115-ФЗ о правовом положении иностранных граждан** | Новый check `immigration_and_work_permits` |
| G7 | **Pension / retirement obligations (unfunded)** — обязательства по пенсионному обеспечению, NPF, unfunded pension liabilities. Legacy defined-benefit (для западных сделок) или НПФ-обязательства. | **75-ФЗ о НПФ; ст. 6 ФЗ о гарантировании прав застрахованных** | Новое поле `pension_obligations_unfunded` в `hr_collective_agreements` |
| G8 | **Equity / LTIP details** — cliff, vesting schedule, forfeiture, условия acceleration. Частично в `hr_key_management`, но equity-специфика не разобрана глубоко. | Договорная практика | Расширение полей в `hr_key_management` |
| G9 | **Employee communications / information obligations** — обязательства информирования работников о сделке, реорганизации, рисках. Срок, форма, содержание. | ТК РФ (ст. 53); Directive 2002/14/EC (для ЕС-компонентов) | Новое поле `employee_communications_obligations` в `hr_collective_agreements` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G10 | **Employee representation bodies (кроме профсоюза)** — совет трудового коллектива, уполномоченные по охране труда, представители работников | Поле в `hr_collective_agreements` |
| G11 | **Disciplinary procedures / termination grounds** — основания увольнения, дисциплинарная ответственность | DEFER — employment-contract-specific |
| G12 | **Whistleblowing** — процедуры сообщения о нарушениях работниками | Поле в `hr_collective_agreements` |
| G13 | **Post-employment obligations: reference, reputation** — рекомендации, репутационные обязательства | DEFER — узко |

#### Дополнительно (низкий / вне scope)

| ID | Риск | Что нужно |
|---|---|---|
| G14 | Collective bargaining process — процедура заключения CBA, представительство работников при переговорах | Вне scope global — специфика CBA как doc-type |
| G15 | Employee inventions / IP assignment — служебные произведения, права работодателя | Cross-ref с `ip_it/*` (G-поле там), не дублировать |
| G16 | Employee stock purchase plans (ESPP) | DEFER — узко, обычно в doc-type |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| ПДн в общем виде (роли, цели, категории, cross-border) | `confidentiality/personal_data_and_dpa` ✅ |
| Data breach notification | `confidentiality/personal_data_and_dpa` ✅ (частично) |
| CoC: определение момента срабатывания, definition of control | `coc/*` ✅ |
| Уступка прав (в т.ч. потенциально трудовые договоры) | `assignment_transfer/*` — частично ✅ |
| Ответственность за нарушение | `liability/*` — частично ✅ |
| Расторжение (общие основания) | `term/*` — частично ✅ |
| IP / служебные произведения | `ip_it/*` — частично ✅ |
| ИБ-контур, ИТ-аутсорсинг | `cyber/*` — частично ✅ |

### 4. Вне scope global

- Трудовой договор как отдельный doc-type (форма ТД, обязательные условия ст. 57 ТК РФ) — `document_types/employment_contract`
- Коллективный договор как отдельный doc-type — `document_types/collective_agreement`
- Конкретные формы: ТД-2, СОУТ-карты, приказы, личные карточки
- Отраслевые требования (медицина, транспорт, банки — квалификационные требования)
- Государственная служба / муниципальная служба — специальный режим
- Мобилизационные предписания / бронирование

### 5. Структурные проблемы группы

- ⚠️ **Порядок `<context>` / `<context_rules>`** — в обоих checks `<context>` идёт **до** `<context_rules>` (в эталоне CoC — наоборот). Не ломает pipeline, но нарушает шаблон. → CONSIDER — унифицировать в отдельном PR.
- ⚠️ **Дубли в nested `keywords`** — в обоих checks есть пересечения regex между уровнями `high` / `medium` / `low` (например, `collective agreement` — в high и low; `non-compete` — в high и low; `vesting` — в medium и low). Структурная anomaly (nested keywords должны быть семантически disjoint). → CONSIDER.
- ⚠️ **`retrieval_profile` — переиспользование** без отдельного «hr» профиля: `hr_collective_agreements` использует `employment_benefits_check`, `hr_key_management` — `change_of_control_check` (из CoC). Возможна неоптимальная выдача. → CONSIDER — возможно, нужен отдельный `hr_check` профиль.
- ⚠️ **`position_bias.preferred_range: [0.0, 1.0]`** в обоих — полный диапазон, без предпочтения (boost 0.10). Может быть намеренно: HR-клаузы могут быть в любом месте договора. → CONSIDER.
- ⚠️ **`enrichment_hints.excluded_segment_types` содержит `schedule`** в обоих — но CBA / retention packages / benefits schedules часто выносятся именно в приложения. Возможен false-negative при retrieval. → CONSIDER.
- ⚠️ **`preferred_clause_functions` содержит дубль `"procedures"`** в `hr_key_management_and_change_of_control` (список из 4 значений, два из них — `procedures`). → CONSIDER — почистить.
- ⚠️ **Внутренняя неконсистентность Шага 5** в `hr_key_management_and_change_of_control`: правило упоминает 4 условия `has_*`, но текст вывода сокращён до «CoC выплат не обнаружено; retention нет». → CONSIDER — уточнить.
- ⚠️ **`description` ↔ `<role>`** — в обоих checks `description` обещает «оценку риска / влияния», `<role>` запрещает оценку. RF9. → CONSIDER, `description` не меняется.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — ПДн работников (HR-специфика) | Новое поле `employee_data_processing_status` в `personal_data_and_dpa` (confidentiality) |
| **P1** | G2 — переход сотрудников при asset deal / outsourcing (ст. 75, 77 ТК РФ) | Новый check `employee_transfer_on_deal` |
| **P1** | G3 — HR compliance reps | Поле `hr_compliance_reps` в `hr_collective_agreements` **или** новый check |
| **P1** | G4 — key employee non-financial retention | Поле в `hr_key_management` |
| P2 | G5 — охрана труда / СОУТ (426-ФЗ) | Поле в `hr_collective_agreements` |
| P2 | G6 — immigration / work permits (115-ФЗ) | Новый check `immigration_and_work_permits` |
| P2 | G7 — unfunded pension obligations (75-ФЗ) | Поле в `hr_collective_agreements` |
| P2 | G8 — equity / LTIP details | Расширение в `hr_key_management` |
| P2 | G9 — employee communications | Поле в `hr_collective_agreements` |
| P3 | G10–G13 | DEFER — backlog |

**Минимум для полноты группы:**
- 2 новых check'а P1: `employee_transfer_on_deal`, `hr_compliance_representations` (или поле).
- 2 поля P1: `employee_data_processing_status` (в confidentiality), `key_employee_nonfinancial_retention`.
- 1 новое поле P2: `health_safety_obligations` (426-ФЗ — универсально для промышленных / производственных сделок).

**Общая оценка:** группа `hr` покрывает два важных блока — **коллективные обязательства** и **индивидуальные M&A-механики для топ-менеджмента**. Однако структура группы **неполная** для сценариев, где HR-риски выходят за рамки CBA и golden parachutes:
- **asset deals / outsourcing** — переход сотрудников (ст. 75 ТК РФ) не покрыт вообще;
- **ПДн работников** — заявлено в cross-ref с `confidentiality`, но HR-специфика (ст. 86–88 ТК РФ) не разобрана;
- **HR compliance reps** — обязательный элемент M&A DD, отсутствует;
- **охрана труда / СОУТ** — универсально для производственных сделок, отсутствует;
- **immigration** — критично для международных сделок, отсутствует.

Для доведения группы до ~85% покрытия рекомендуется **минимум 2 новых check'а + 4–5 новых полей**.


## Группа: ip_it

**Директория:** `playbooks/global_checks/ip_it/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~55% — покрыты параметры лицензии, передаваемость, ownership / chain of title, доступ к ИТ-системам. Отсутствуют: OSS-комплаенс, IP reps & warranties, IP indemnity, software escrow, режим коммерческой тайны, joint IP.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `ip_license_scope_and_usage` | Параметры предоставленной лицензии: тип (exclusive / non-exclusive / sole), территория, срок, field of use, сублицензирование |
| 2 | `ip_license_transferability_and_change_of_control` | Передаваемость лицензии: аффилированным лицам, при M&A / реорганизации, поведение при CoC, требование согласия лицензиара |
| 3 | `ip_ownership_and_assignments` | Принадлежность IP, chain of title, assignment от основателей / сотрудников / подрядчиков, полнота scope, pre-existing / third-party IP |
| 4 | `it_systems_access_and_data_export` | Доступ к ИТ-системам: основания и жёсткость приостановки, срок уведомления, право на экспорт данных, окно / форматы, retention / deletion, backup / restore |

**Что это даёт в сумме:** проверяются четыре изолированных блока — параметры входящей лицензии, передаваемость прав, чистота ownership / chain of title, операционный контур IT access / data exit.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Open source compliance / OSS-риск** — использование OSS-компонентов, copyleft / GPL / AGPL contamination, обязательства по раскрытию исходного кода, attribution, SBOM. Для любого договора с ПО — стандартный tech DD, критично для M&A. | ст. 1235, 1236 ГК РФ; GPL / Apache / MIT / AGPL | Новый check `open_source_compliance` |
| G2 | **IP representations & warranties** — заявления о принадлежности, отсутствии обременений, отсутствии претензий третьих лиц, об отсутствии нарушений. Стандартные reps в M&A / tech-контрактах. | Практика M&A; ст. 431.2 ГК РФ | Новый check `ip_representations_and_warranties` **или** поле `ip_reps_present` в `ip_ownership_and_assignments` |
| G3 | **IP indemnification** — возмещение потерь при претензиях третьих лиц о нарушении IP; scope, exclusions, процедура, cap / basket. | ст. 406.1 ГК РФ; договорная практика | Новый check `ip_indemnification` |
| G4 | **Software escrow / source code escrow** — доступ к исходному коду при банкротстве / прекращении поддержки провайдера. Критично для SaaS / mission-critical IT-систем. | Договорная практика | Поле `source_code_escrow` в `it_systems_access_and_data_export` **или** новый check `software_escrow` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G5 | **Режим коммерческой тайны** — как Target защищает know-how / trade secrets: NDA-режим, перечень сведений, доступ по списку, учёт носителей. | 98-ФЗ «О коммерческой тайне»; ст. 1465 ГК РФ | Поле `trade_secret_regime` в `confidentiality_and_trade_secrets` **или** отдельный check `trade_secret_protection` |
| G6 | **Joint IP / co-ownership** — совместная разработка, co-owned IP, распределение прав на результаты совместной деятельности. Часто в JV / R&D. | ст. 1229, 1258 ГК РФ; ст. 1298 ГК РФ | Новый check `joint_ip_and_co_ownership` **или** поле в `ip_ownership_and_assignments` |
| G7 | **Employee inventions / inventor remuneration** — право автора служебного произведения на вознаграждение, риски исков от бывших сотрудников. | ст. 1295 п. 2, ст. 1370 ГК РФ | Поле `employee_inventor_remuneration` в `ip_ownership_and_assignments` |
| G8 | **Inbound third-party IP dependencies** — от каких внешних лицензий / OSS / SaaS критически зависит бизнес Target; отзывные лицензии. | Договорная практика | Поле `inbound_ip_dependencies` в `ip_ownership_and_assignments` |
| G9 | **IP registrations / recordals** — статус регистрации ТЗ / патентов / программ, pending applications, recordals сделок об отчуждении. | ст. 1232, 1234 п. 4, 1490 ГК РФ | Поле `ip_registration_status` в `ip_ownership_and_assignments` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G10 | Domain names / digital assets | Поле `digital_assets_present` в `ip_ownership_and_assignments` |
| G11 | Copyright notices / attribution requirements | Поле в `ip_license_scope_and_usage` |
| G12 | Patents FTO (freedom to operate) | DEFER — узко |
| G13 | Covenants not to sue / non-assertion | DEFER — узко |
| G14 | AI-generated content / AI-IP | DEFER — emerging topic |
| G15 | Data-as-asset / data ownership | Cross-ref с `confidentiality/personal_data_and_dpa` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Personal data (роли, цели, категории) | `confidentiality/personal_data_and_dpa` ✅ |
| Коммерческая тайна в общем виде | `confidentiality/confidentiality_and_trade_secrets` — частично ✅ |
| Уступка прав (в т.ч. IP) | `assignment_transfer/*` — частично ✅ |
| Change of control для лицензий | `coc/*` ✅ |
| Ответственность за нарушение reps | `liability/*` — частично ✅ |
| CoC для key management / vesting IP | `hr/hr_key_management_and_change_of_control` ✅ |
| ИБ-контур провайдера, SLA | `cyber/outsourced_it_and_security_risk` ✅ |

### 4. Вне scope global

- IP-специфика отраслей (pharma, media, промышленность)
- IP-регистрация в специализированных реестрах (USPTO, EPO, WIPO)
- Domain names arbitration (UDRP, WIPO)
- Patentability / validity / infringement opinions — advisory
- Регистрационные действия в Роспатенте — operational

### 5. Структурные проблемы группы

- ⚠️ **Тематическая путаница:** `it_systems_access_and_data_export` в `ip_it/`, но по содержанию — termination / IT ops, не IP. Возможные целевые группы: `termination/`, `cyber/`, отдельная `it_ops/`. → CONSIDER.
- ⚠️ **`retrieval_profile` reuse:** `license_scope_check` используется и в `ip_license_scope_and_usage`, и в `ip_license_transferability_and_change_of_control`. → CONSIDER — возможно, нужен отдельный `ip_transferability_check`.
- ⚠️ **Дубли в nested `keywords`** во всех 4 checks (2–9 пар). → CONSIDER.
- ⚠️ **Порядок `<context>` / `<context_rules>`** — во всех 4 `<context>` до `<context_rules>` (в CoC — наоборот). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** — в 2 checks (`ip_ownership_and_assignments`, `it_systems_access_and_data_export`). → CONSIDER.
- ⚠️ **Дубль `store_payload: true`** — в `ip_ownership_and_assignments` и `it_systems_access_and_data_export`. Реальная anomaly. → APPLY NOW (исправлено при подготовке YAML).
- ⚠️ **Дубль `"obligations"`** в `preferred_clause_functions` у `it_systems_access_and_data_export`. → CONSIDER.
- ⚠️ **Смешение founders / employees** в `has_assignments_from_founders_and_employees`. → CONSIDER.
- ⚠️ **`position_bias.preferred_range: [0.0, 1.0]`** во всех 4. → CONSIDER.
- ⚠️ **Малая численность группы** — 4 checks на такой широкий домен недостаточно.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — OSS compliance | Новый check `open_source_compliance` |
| **P1** | G2 — IP reps & warranties | Новый check `ip_representations_and_warranties` |
| **P1** | G3 — IP indemnification | Новый check `ip_indemnification` |
| **P1** | G4 — software escrow | Поле `source_code_escrow` в `it_systems_access_and_data_export` |
| P2 | G5 — режим коммерческой тайны | Поле в `confidentiality_and_trade_secrets` |
| P2 | G6 — joint IP / co-ownership | Поле или новый check |
| P2 | G7 — inventor remuneration | Поле в `ip_ownership_and_assignments` |
| P2 | G8 — inbound IP dependencies | Поле в `ip_ownership_and_assignments` |
| P2 | G9 — IP registrations | Поле в `ip_ownership_and_assignments` |
| P3 | G10–G15 | DEFER — backlog |

**Минимум для полноты группы:**
- 3 новых check'а P1: `open_source_compliance`, `ip_representations_and_warranties`, `ip_indemnification`.
- 1 новое поле P1: `source_code_escrow`.
- 3–4 поля P2 (trade secret regime, joint IP, inventor remuneration, registrations).

**Общая оценка:** группа `ip_it` покрывает фундамент IP-периметра — параметры лицензии, передаваемость, ownership / chain of title, IT access / data exit. Пропускает критический для tech / M&A слой: OSS-комплаенс, IP reps & warranties, IP indemnity, software escrow, trade secrets режим, joint IP / employee inventions. Также есть тематическая путаница с `it_systems_access_and_data_export`. Для доведения до ~85% покрытия требуется минимум 3 новых check'а + 5 новых полей.



## Группа: liability

**Директория:** `playbooks/global_checks/liability/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~55% — покрыто ядро денежной ответственности (scope / cap / basket / carve-out / exclusions / cross-default), но отсутствуют процедурная часть indemnity, временные рамки предъявления претензий, неденежные remedies, set-off, insurance-механизмы.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `cross_default_and_acceleration` | Cross-default / cross-acceleration: дефолт по другим обязательствам, акселерация другого долга, scope, threshold, grace period, механизм триггера |
| 2 | `liability_and_indemnity_scope` | Общий объём ответственности: limited / unlimited, масштаб indemnity, в чью пользу, значимые штрафы |
| 3 | `liability_caps_and_baskets` | Структура лимитов: cap, basket (tipping / deductible), de minimis, carve-outs для ключевых рисков |
| 4 | `liability_exclusions` | Исключения из ответственности: indirect / consequential / special / punitive, loss of profit / business / revenue, направленность |

**Что это даёт в сумме:** покрыта денежная (компенсационная) ответственность — что взыскивается, в каком объёме, с какими ограничениями. Каскадные дефолты (cross-default) — тоже. Пропущены процедурная, временная, неденежная и защитная части liability-контура.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Force majeure / освобождение от ответственности** — основания освобождения, критерии квалификации, уведомление, сроки, влияние на сроки исполнения и право на расторжение. | ст. 401 п. 3 ГК РФ; ст. 417 ГК РФ; ст. 328 ГК РФ | Новый check `force_majeure_and_excused_nonperformance` **ИЛИ** проверить `term/*` |
| G2 | **Indemnity procedure** — notice, cooperation, control of defense, settlement consent, third-party claims handling. | Договорная практика; ст. 406.1 ГК РФ | Новый check `indemnity_procedure` **или** 3 поля в `liability_and_indemnity_scope` |
| G3 | **Limitation period for claims / survival** — временные рамки, survival reps & warranties. Критично для M&A / long-term contracts. | ст. 196, 197 ГК РФ; ст. 431.2 ГК РФ | Новый check `limitation_periods_and_survival` |
| G4 | **Set-off / netting** — право зачёта встречных требований, влияние на реальный денежный поток. | ст. 410–412 ГК РФ | Поле `set_off_rights` в `liability_and_indemnity_scope` |
| G5 | **Specific performance / injunctive relief** — неденежные способы защиты. | ст. 12, 396 ГК РФ | Поле `non_monetary_remedies` в `liability_and_indemnity_scope` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G6 | **Liquidated damages / penalty — детальная механика** — ставки, cumulative vs exclusive remedy, enforceability, соответствие ст. 333 ГК РФ. | ст. 330–333 ГК РФ | Поле `liquidated_damages_mechanics` или отдельный check |
| G7 | **Consequential damages — определение и foreseeability** — что считается «косвенными», критерий предвидимости. | ст. 15, 393 ГК РФ; Hadley v Baxendale | Поле `consequential_damages_definition` |
| G8 | **Mitigation duty** — обязанность уменьшать убытки, вина кредитора. | ст. 404 ГК РФ | Поле `mitigation_duty` в `liability_and_indemnity_scope` |
| G9 | **Gross negligence / willful misconduct standard** — стандарты вины, ограничения на возможность ограничения ответственности. | ст. 401 п. 4 ГК РФ | Поле `gross_negligence_standard` в `liability_caps_and_baskets` |
| G10 | **Insurance / risk allocation** — обязательства страхования, соотношение с договорной ответственностью. | Договорная практика | Поле `insurance_requirements` в `liability_and_indemnity_scope` |
| G11 | **Contribution / joint liability / регресс** | ст. 322–325 ГК РФ | DEFER — узко |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G12 | Punitive damages (cross-border) | Поле в `liability_exclusions` |
| G13 | Currency / interest on damages | Поле в `liability_and_indemnity_scope` |
| G14 | Tax gross-up on indemnity payments | Поле / cross-ref с tax |
| G15 | Cap erosion / reinstatement | Поле в `liability_caps_and_baskets` |
| G16 | Damages for late payment / statutory interest | Cross-ref с `finance/payment_terms` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Расторжение и его последствия | `term/*` — частично ✅ |
| Force majeure (возможно) | `term/*` — требует проверки ⚠️ |
| Change of control → последствия | `coc/*` ✅ |
| IP indemnity | `ip_it/*` — G3 в предыдущем gap-анализе ⚠️ |
| Data breach liability | `confidentiality/*` — частично ✅ |
| Cybersecurity liability | `cyber/*` — частично ✅ |
| Sanctions liability | `sanctions/*` — частично ✅ |
| Уступка → liability | `assignment_transfer/*` — частично ✅ |
| Ответственность key management при CoC | `hr/*` ✅ |

### 4. Вне scope global

- Product liability (специфика производителей)
- Environmental liability (регуляторика, страхование)
- Professional liability (аудит, консалтинг, юристы)
- Отраслевые стандарты страховых сумм (банки, авиация)
- Экспортный контроль liability (regulatory)
- Катастрофическая ответственность / ядерная энергетика

### 5. Структурные проблемы группы

- ⚠️ **`retrieval_profile` reuse:** `liability_cap_check` в `liability_caps_and_baskets` и `liability_exclusions`. → CONSIDER.
- ⚠️ **Дубли `"limitations"` в `preferred_clause_functions`** — в 3 из 4 checks. Структурная anomaly. → APPLY NOW.
- ⚠️ **RF8 mismatch:** `liability_exclusions` — `severity: medium` ≠ `severity_if_fail: high`. → CONSIDER as designed.
- ⚠️ **Порядок `<context>` до `<context_rules>`** — во всех 4 checks. → CONSIDER.
- ⚠️ **Дубли в nested `keywords`** — во всех 4 (5–10 пар каждый). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** — в 3 из 4 checks. → CONSIDER.
- ⚠️ **Отсутствие взаимных cross-refs между checks группы.** → DEFER.
- ⚠️ **Группа изолирована** — только денежная ответственность, без процедурной и защитной части.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — force majeure / освобождение | Новый check **ИЛИ** проверить `term/*` |
| **P1** | G2 — indemnity procedure | Новый check или 3 поля |
| **P1** | G3 — limitation period / survival | Новый check |
| **P1** | G4 — set-off / netting | Поле |
| **P1** | G5 — non-monetary remedies | Поле |
| P2 | G6 — liquidated damages mechanics | Поле или check |
| P2 | G7 — consequential damages definition | Поле |
| P2 | G8 — mitigation duty | Поле |
| P2 | G9 — gross negligence standard | Поле |
| P2 | G10 — insurance / risk allocation | Поле |
| P3 | G11–G16 | DEFER |

**Минимум для полноты группы:**
- Обязательная проверка: где покрыт force majeure.
- 2 новых check'а P1: `indemnity_procedure`, `limitation_periods_and_survival`.
- 3 поля P1: `set_off_rights`, `non_monetary_remedies` + force majeure (если нигде).
- 3 поля P2: `consequential_damages_definition`, `mitigation_duty`, `insurance_requirements`.

**Общая оценка:** группа `liability` покрывает ядро денежной ответственности — scope, caps, basket, carve-outs, exclusions, cross-default. Хорошо согласована внутри. Однако пропускает процедурную часть indemnity, временные рамки предъявления претензий, неденежные remedies, set-off, insurance-механизмы, force majeure (если не в `term`). Для доведения до ~85% требуется минимум 2 новых check'а + 5–6 новых полей.



## Группа: regulatory

**Директория:** `playbooks/global_checks/regulatory/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 3 из 3
**Статус группы:** покрытие ~55% — покрыты антикоррупция + RPT, отраслевой комплаенс, лицензии / разрешения. Отсутствуют AML / KYC, антимонопольный контроль, экспортный контроль, data protection regulatory, ESG.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `anti_corruption_and_related_parties` | Антикоррупция (FCPA / UK Bribery Act / ФЗ-273), кодексы этики, права аудита комплаенса, whistleblowing, RPT-регулирование (arm's length, корпоративные одобрения) |
| 2 | `regulatory_industry_compliance` | Отраслевой комплаенс (финансы, медицина, телеком, энергетика, образование, защита данных), регуляторные события (проверки, расследования, штрафы, enforcement), заверения об отсутствии нарушений, remedial-меры |
| 3 | `regulatory_licenses_and_permits` | Ключевые лицензии / разрешения / аккредитации, держатель, зависимость от структуры владения, механизм сохранения при CoC |

**Что это даёт в сумме:** покрыты три изолированных блока — антикоррупция + RPT, отраслевой комплаенс в общем виде, лицензионный контур. Содержательно глубоко, но обходит стороной несколько крупных регуляторных тем.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **AML / KYC / ПОД/ФТ** — противодействие легализации, KYC, источники средств, проверка UBO. Обязательно для банков, финорганизаций, regulated entities. | 115-ФЗ; FATF Recommendations; 5-я и 6-я директивы ЕС (AMLD) | Новый check `anti_money_laundering_and_kyc` |
| G2 | **Антимонопольный контроль / merger control** — одобрение ФАС / зарубежных регуляторов, пороги, сроки, gun-jumping, remedies. | ФЗ-135 (гл. 7); ст. 27–31; Регламент ЕС 139/2004; HSR Act (США) | Новый check `antitrust_and_merger_control` |
| G3 | **Экспортный контроль / dual-use / военные технологии** — контроль экспорта, лицензии, ECCN / EAR, ITAR, re-export restrictions. | 183-ФЗ; EAR / ITAR (US); Wassenaar Arrangement | Новый check `export_control_and_dual_use` |
| G4 | **Data protection — регуляторный compliance** — соответствие 152-ФЗ (уведомление РКН, локальное хранение), GDPR (DPO, DPIA, breach notification), cross-border transfers. | 152-ФЗ; GDPR (EU 2016/679); CCPA | Новый check `data_protection_regulatory_compliance` **или** расширение `regulatory_industry_compliance` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G5 | **ESG / environmental compliance** — экологические обязательства, carbon / emissions, sustainability disclosure, CSRD / CSDDD. | 7-ФЗ; EU CSRD / CSDDD; TCFD | Новый check `esg_and_environmental_compliance` |
| G6 | **Whistleblowing standalone** — отдельный режим защиты информаторов. Частично в `anti_corruption`. | EU Directive 2019/1937 | Отдельный check или расширение `anti_corruption` |
| G7 | **Sanctions compliance — cross-ref** — проверить, что не дублируется с `sanctions/*`. | OFAC / EU sanctions / UK OFSI | Cross-ref |
| G8 | **Государственный оборонный заказ / гостайна** — если применимо: режим гостайны, допуски, ФСБ / ФСТЭК. | 5485-1; 44-ФЗ / 223-ФЗ | Новый check или DEFER |
| G9 | **Профессиональные лицензии сотрудников** — допуски, которые должны иметь конкретные сотрудники. | Профстандарты | Расширение `regulatory_licenses_and_permits` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G10 | Advertising / marketing compliance (38-ФЗ) | Поле в `regulatory_industry_compliance` |
| G11 | Labour / immigration regulatory | Cross-ref с `hr/*` |
| G12 | Tax regulatory compliance | Cross-ref с tax |
| G13 | Consumer protection | Поле или отдельный check |
| G14 | Product regulatory (сертификация, ГОСТ / CE) | Отдельный check — DEFER |
| G15 | Transport / logistics regulatory | DEFER — узко |
| G16 | Regulatory reporting (ЦБ, Росстат) | Поле в `regulatory_industry_compliance` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Санкции / sanctions compliance | `sanctions/*` ✅ |
| Personal data (роли, цели, категории, cross-border) | `confidentiality/personal_data_and_dpa` — частично ✅ |
| Data breach notification | `confidentiality/*` — частично ✅ |
| Cybersecurity policies / incidents | `cyber/*` ✅ |
| ИТ-аутсорсинг, SLA | `cyber/outsourced_it_and_security_risk` ✅ |
| Корпоративные одобрения | `formal/corporate_approvals_and_transaction_qualification` — частично ✅ |
| HR compliance | `hr/*` — частично ✅ |
| Коммерческая тайна / trade secret regime | `confidentiality/*` — частично ✅ |
| IP / OSS-комплаенс | `ip_it/*` — частично ✅ |

### 4. Вне scope global

- Отраслевые специфики (авиация, атом, оборонная промышленность) — doc-type
- Securities law / публичные компании (SEC filings, MAR, insider trading)
- Tax regulatory compliance — tax-specialized
- Специализированные режимы иностранных юрисдикций (CFIUS, FIRB, DPA)
- Страховое регулирование сверх общих reps
- Регистрационные действия в Роспатенте / РКН / Росздравнадзоре — operational
- Специфические торговые ограничения (WTO, тарифы)

### 5. Структурные проблемы группы

- ⚠️ **Группа изолирована** — 3 checks покрывают 3 разных темы, но не образуют связного regulatory-контура. Отсутствуют AML, antitrust, export control, data protection regulatory.
- ⚠️ **`retrieval_profile` reuse:** `sanctions_compliance_check` (anti_corruption), `warranties_check` (industry_compliance), `registration_check` (licenses_and_permits). → CONSIDER.
- ⚠️ **RF8 mismatch:** `regulatory_licenses_and_permits` — `severity: high` ≠ `severity_if_fail: critical`. → CONSIDER as designed.
- ⚠️ **Порядок `<context>` до `<context_rules>`** — во всех 3 checks. → CONSIDER.
- ⚠️ **Дубли в nested `keywords`** — во всех 3 (7–10 пар каждый). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** — во всех 3 checks. → CONSIDER.
- ⚠️ **`mentions_regulatory_events` с 4 значениями** (`yes / none_mentioned / no / unclear`) — продуманная семантика, но не описана в `description`. → CONSIDER.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — AML / KYC / ПОД/ФТ | Новый check `anti_money_laundering_and_kyc` |
| **P1** | G2 — антимонопольный контроль / merger control | Новый check `antitrust_and_merger_control` |
| **P1** | G3 — экспортный контроль / dual-use | Новый check `export_control_and_dual_use` |
| **P1** | G4 — data protection (регуляторный) | Новый check или расширение |
| P2 | G5 — ESG / environmental compliance | Новый check |
| P2 | G6 — whistleblowing standalone | Расширение `anti_corruption` |
| P2 | G7 — sanctions cross-ref | Проверить |
| P2 | G8 — гостайна / оборонный заказ | Новый check или DEFER |
| P2 | G9 — профессиональные лицензии | Расширение `regulatory_licenses_and_permits` |
| P3 | G10–G16 | DEFER — backlog |

**Минимум для полноты группы:**
- 2 новых check'а P1: `anti_money_laundering_and_kyc`, `antitrust_and_merger_control`.
- 1 новый check P1: `export_control_and_dual_use`.
- 1 новый check P1 или расширение: data protection regulatory.
- 3 поля P2: ESG reps, whistleblowing standalone, foreign regulatory approvals.
- Проверить cross-ref с `sanctions/*`.

**Общая оценка:** группа `regulatory` покрывает антикоррупцию + RPT, отраслевой комплаенс в общем виде, лицензионный контур. Пропускает критичные для M&A темы: AML / KYC, antitrust / merger control, export control, data protection regulatory, ESG. Группа тематически изолирована, не образует связного regulatory-контура. Для доведения до ~85% требуется минимум 3 новых check'а P1 + 3 поля P2.



## Группа: sanctions

**Директория:** `playbooks/global_checks/sanctions/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 3 из 3
**Статус группы:** покрытие ~50% — покрыты AML/KYC, экспортный контроль, базовые санкционные оговорки. Отсутствуют: secondary sanctions, sectoral sanctions, geographic embargoes, ownership/control test, wind-down/licensing, FDI screening, anti-boycott.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `aml_kyc` | AML/KYC-обязательства: идентификация клиентов, детализация KYC, periodic update, UBO disclosure, transaction monitoring, ссылки на ФЗ-115 / FATF / EU AML Directives, право контрагента на приостановку |
| 2 | `export_control` | Экспортный контроль: применимые режимы (ITAR / EAR / EU dual-use / ФЗ-183), уровень детализации, обязательства по соблюдению, экспортные лицензии, ограничения re-export |
| 3 | `sanctions_clauses` | Санкционные оговорки: reps, охват (UBO, аффилированные), покрываемые режимы, compliance obligations, notification, event consequences, триггер (actual vs risk-based), mitigation |

**Что это даёт в сумме:** покрыты три изолированных блока — AML/KYC, экспортный контроль, базовые санкционные reps.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет (универсальные для cross-border сделок)

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Secondary sanctions** — US secondary sanctions (CAATSA, IFCA), EU blocking statute 2271/96, EU Anti-Coercion Instrument | CAATSA; IFCA; EU 2271/96 | Поле `has_secondary_sanctions_risk` в `sanctions_clauses` или новый check |
| G2 | **Sectoral sanctions (SSI, EU sectoral)** — запрет конкретных типов транзакций, а не полный blocking | OFAC SSI; EU Council Regulations | Поле `has_sectoral_sanctions_provisions` |
| G3 | **Geographic embargoes** — запрет операций с целыми странами / регионами (Cuba, Iran, NK, Syria, Crimea) | 31 CFR Part 515; EU Reg 833/2014 | Поле `has_geographic_embargo_restrictions` |
| G4 | **Ongoing sanctions screening obligation** — периодический screening, отличающийся от AML monitoring | OFAC Framework; EU best practices | Поле `has_ongoing_screening_obligation` |
| G5 | **Anti-circumvention / anti-evasion** — запрет структурирования сделок для обхода санкций | OFAC Russia-related; EU Art. 12 Reg 833/2014 | Поле `has_anti_circumvention_clause` |
| G6 | **Ownership and control test (50% rule)** — SDN owns 50%+ → entity blocked | OFAC 50% Rule; EU / UK ownership & control | Поле `has_ownership_control_test_coverage` |
| G7 | **Wind-down / grandfathering / licensing** — порядок завершения, GLs, authorisations | OFAC GLs; EU authorisations | Поле `has_wind_down_provisions` |
| G8 | **FDI screening / investment approval** — CFIUS, EU 2019/452, UK NSIA, ФЗ-57 | CFIUS; EU 2019/452; UK NSIA; ФЗ-57 | Новый check `fdi_screening_and_investment_approvals` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G9 | Price cap compliance (oil, refined products) | G7 Oil Price Cap; EU 2022/1904 | Поле `has_price_cap_compliance_obligations` |
| G10 | Vessel / aircraft / port restrictions | OFAC Maritime guidance | Поле `has_vessel_aircraft_restrictions` |
| G11 | Deemed export / re-export | 15 CFR §734.2(b); EU 2021/821 | Поле `has_deemed_export_provisions` в `export_control` |
| G12 | Ongoing end-use / end-user monitoring | BIS KYC guidance | Поле `has_ongoing_end_use_monitoring` в `export_control` |
| G13 | Anti-boycott / blocking statutes | EU 2271/96; 15 CFR Part 760 | Новый check `anti_boycott_and_blocking_statutes` |
| G14 | Sanctions Compliance Program (SCP) adequacy | OFAC Framework; BIS Guidelines | Поле `has_scp_representation` |
| G15 | Sanctions-specific reporting obligations | 31 CFR Part 501; ФЗ-115 | Поле `has_sanctions_reporting_obligation` |
| G16 | PEP screening + adverse media | FATF Rec 12; EU 4AMLD | Поле `has_pep_screening` в `aml_kyc` |
| G17 | Trade-based money laundering (TBML) | FATF TBML guidance | Поле `has_tbml_controls` в `aml_kyc` |
| G18 | Illegality / frustration clauses | Common law; ст. 401, 416, 417 ГК РФ | Поле `has_illegality_clause` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G19 | Cryptocurrency / virtual assets sanctions compliance | Поле `has_crypto_sanctions_coverage` |
| G20 | Humanitarian exemptions / carve-outs | Поле `has_humanitarian_exemptions` |
| G21 | Debarment / exclusion lists (World Bank, SAM) | Новый check |
| G22 | Human rights due diligence / conflict minerals | Cross-ref с ESG |
| G23 | Data / technology transfer restrictions as standalone | Расширение `export_control` |
| G24 | Sanctions in financing documents | Cross-ref с `finance/*`, `liability/*` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Ответственность за нарушение санкций | `liability/*` — частично ✅ |
| Санкции как termination ground | `term/*` — требует проверки ⚠️ |
| Санкционные reps в M&A | `rw/rw_specific_and_survival` — частично ✅ |
| Payment refusal / blocked funds | `finance/payment_terms_and_structures` — частично ✅ |
| Антимонопольный контроль | `regulatory/*` — gap G2 |
| FDI screening | `regulatory/*` — gap G2 |
| Regulatory compliance в общем | `regulatory/regulatory_industry_compliance` ✅ |
| Data protection / cross-border | `confidentiality/personal_data_and_dpa` — частично ✅ |
| ИБ-контур, ИТ-аутсорсинг | `cyber/*` ✅ |

### 4. Вне scope global

- Отраслевые санкционные режимы (aviation, defense, energy, banking) — doc-type / regulatory
- Insurance-specific sanctions clauses
- Debarment в публичных закупках в специфических юрисдикциях
- Antiquities / cultural property sanctions
- Correspondent banking / nested accounts — специфика банков
- Crypto exchanges / VASP-специфика

### 5. Структурные проблемы группы

- ⚠️ **Группа тематически изолирована.** 3 checks — 3 независимые темы, не образуют связного sanctions-контура.
- ⚠️ **`retrieval_profile` reuse:** `sanctions_compliance_check` во всех 3 checks. → CONSIDER.
- ⚠️ **`preferred_clause_functions` содержит дубли** в `aml_kyc` (`obligations` ×2), `export_control` (`obligations` ×2). → CONSIDER.
- ⚠️ **Порядок `<context>` до `<context_rules>`** во всех 3 checks. → CONSIDER.
- ⚠️ **Дубли в nested `keywords`** — во всех 3 (7–10 пар). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** во всех 3. → CONSIDER.
- ⚠️ **Опечатка `налиличие` в `sanctions_clauses.description`** — исправить при следующем коммите (obligatory field).
- ⚠️ **`export_control` Step 0 без формального bullet `- "present" — ...`** — использует существующее status-поле напрямую. → CONSIDER.
- ⚠️ **Отсутствие взаимных cross-refs между checks группы.** → DEFER.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — secondary sanctions | Поле или отдельный check |
| **P1** | G2 — sectoral sanctions | Поле |
| **P1** | G3 — geographic embargoes | Поле |
| **P1** | G4 — ongoing screening obligation | Поле |
| **P1** | G5 — anti-circumvention | Поле |
| **P1** | G6 — ownership / control test | Поле |
| **P1** | G7 — wind-down / licensing | Поле |
| **P1** | G8 — FDI screening | Новый check |
| P2 | G9–G18 | Поля + 1 новый check |
| P3 | G19–G24 | DEFER |

**Минимум для полноты группы:**
- 1 новый check P1: `fdi_screening_and_investment_approvals`.
- 7 новых полей P1 в `sanctions_clauses`: secondary / sectoral / geographic / ongoing screening / anti-circumvention / ownership control / wind-down.
- 2 новых поля P2 в `export_control` + 2 в `aml_kyc`.
- 1 новый check P2: `anti_boycott_and_blocking_statutes`.

**Общая оценка:** группа покрывает базовый compliance-минимум, но пропускает критичные для cross-border / M&A темы: secondary sanctions, sectoral sanctions, geographic embargoes, 50% rule, wind-down/licensing, FDI screening, anti-circumvention, ongoing screening. Для доведения до ~85% требуется минимум 1 новый check + 11 новых полей.


## Группа: rw

**Директория:** `playbooks/global_checks/rw/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~60% — покрыты MAC/MAE, фундаментальные reps, финансовые / операционные reps, специальные reps + survival. Отсутствуют capitalization / subsidiaries, environmental, real property / leases, insurance, bring-down, disclosure schedule mechanism, sandbagging, materiality scrape, interim covenants.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `mac_mae` | MAC/MAE-клауза: наличие, количественные пороги, carve-outs (отраслевые / макро / законодательные), полные vs частичные, последствия (termination / price_adjustment / suspension / acceleration / condition_only), бенефициар |
| 2 | `rw_financial_and_operational` | Финансовые reps: достоверность отчётности (GAAP / IFRS / МСФО / РСБУ), отсутствие скрытых обязательств, действительность существенных договоров, трудовые отношения / HR |
| 3 | `rw_fundamental` | Фундаментальные reps: статус и существование, полномочия, право собственности (title), отсутствие конфликтов, general compliance; qualifiers (knowledge, materiality, disclosed exceptions) |
| 4 | `rw_specific_and_survival` | Специальные reps: налоговые, санкционные, litigation, комплаенс / AML / антикоррупция, IP / обременения; knowledge qualifiers; survival period |

**Что это даёт в сумме:** покрыты 4 базовых блока M&A reps & warranties.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Capitalization / subsidiaries / corporate structure reps** — структура капитала, доли / акции, обременения, дочерние компании, ownership chain | ст. 66.2, 90, 99 ГК РФ; практика M&A | Новый check `rw_capitalization_and_subsidiaries` или поле в `rw_fundamental` |
| G2 | **Environmental reps** — соответствие экологическому законодательству, разрешения, ответственность за загрязнение | 7-ФЗ; отраслевые нормы | Новый check `rw_environmental` |
| G3 | **Real property / leases reps** — право собственности на недвижимость, аренда, обременения, кадастр | ст. 130–132, 549, 606 ГК РФ | Новый check `rw_real_property_and_leases` |
| G4 | **Insurance reps** — наличие и достаточность покрытия, claims, соответствие полисов | Закон РФ № 4015-1 | Новый check или поле `has_insurance_reps` |
| G5 | **Bring-down / closing reps** — подтверждение reps на дату closing | Практика M&A (ABA MSA) | Поле `has_bring_down_mechanism` или новый check |
| G6 | **Disclosure schedule / letter mechanism** — структура раскрытий, general vs specific disclosure | Практика M&A | Поле `has_disclosure_schedule_mechanism` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G7 | IT / data / cybersecurity reps | 152-ФЗ; GDPR | Поле `has_it_data_reps` |
| G8 | AML reps (специфические) | 115-ФЗ | Проверить / расширить |
| G9 | Employee benefits / pension reps | 75-ФЗ; 167-ФЗ | Расширить `rw_employment_hr` |
| G10 | IP reps (детально) | ст. 1225–1551 ГК РФ | Расширить `rw_ip_encumbrances` |
| G11 | Anti-corruption reps (как reps, не policy) | ФЗ-273; FCPA; UKBA | Расширить `rw_compliance_specific` |
| G12 | Product liability / warranty reps | ЗоЗПП; ТР ТС | Новое поле `has_product_reps` |
| G13 | Anti-sandbagging / pro-sandbagging | Common law / договорная практика | Поле `has_sandbagging_clause` |
| G14 | Materiality scrape | Практика M&A | Поле `has_materiality_scrape` |
| G15 | Interim covenants / conduct of business | Практика M&A | Новый check `rw_interim_covenants` |
| G16 | Related party transactions reps | ст. 45 14-ФЗ; ст. 81–84 208-ФЗ | Поле `has_rpt_reps` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G17 | Compliance with sector regulations as reps | Cross-ref с `regulatory/*` |
| G18 | Books and records reps | Поле в `rw_financial_and_operational` |
| G19 | Sanctions / export control as reps | Cross-ref с `sanctions/*` |
| G20 | Anti-dumping / trade remedies | Узко |
| G21 | Government contracts reps | Отдельный домен |
| G22 | Franchises / distribution reps | Отдельный домен |
| G23 | Customer / supplier concentration | Поле в `rw_financial_and_operational` |
| G24 | R&D / pipeline reps | Отдельный домен |
| G25 | Major customers / suppliers relationships | DEFER |
| G26 | Undisclosed side letters | Cross-ref с `formal/document_completeness` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Санкции / экспортный контроль | `sanctions/*` — частично ✅ |
| AML/KYC | `sanctions/aml_kyc` — частично ✅ |
| IP reps | `ip_it/ip_ownership_and_assignments` — частично ✅ |
| Ответственность | `liability/*` — частично ✅ |
| Limitation period | `disputes/*` — частично ✅ |
| CoC reps | `coc/*` — частично ✅ |
| HR reps | `hr/*` — частично ✅ |
| Regulatory compliance | `regulatory/*` — частично ✅ |
| Data protection | `confidentiality/personal_data_and_dpa` — частично ✅ |
| ИБ-контур | `cyber/*` — частично ✅ |
| Существенные договоры | `formal/document_completeness_and_side_letters` — частично ✅ |

### 4. Вне scope global

- Отраслевые reps (banking, pharma, energy, telecom)
- W&I insurance interplay
- Reps по mining rights / spectrum / special assets
- Reps по SPV / fund structures
- Transfer pricing reps
- Reps по government contracts / franchises
- Reps по R&D pipeline

### 5. Структурные проблемы группы

- ⚠️ **Группа тематически изолирована.** 4 checks — 4 разных блока, но не образуют связного reps-контура. Не покрыты capitalization, subsidiaries, real property, insurance, environmental, IT/data.
- ⚠️ **`retrieval_profile` reuse:** `warranties_check` во всех 4 checks. → CONSIDER.
- ⚠️ **Порядок `<context>` до `<context_rules>`** во всех 4 checks. → CONSIDER.
- ⚠️ **Дубли в nested `keywords`** — во всех 4 (3–10 пар). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** — в 3 из 4. → CONSIDER.
- ⚠️ **RF8 mismatch:** `rw_fundamental` — `severity_if_fail: critical` ≠ `severity: high`. → CONSIDER as designed.
- ⚠️ **Дубли в `retrieval.preferred_unit_types` (`general_provision` ×2)** и `enrichment_hints.preferred_clause_functions` (`procedures` ×2) в `mac_mae`. → CONSIDER — почистить.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — capitalization / subsidiaries | Новый check или поле |
| **P1** | G2 — environmental | Новый check |
| **P1** | G3 — real property / leases | Новый check |
| **P1** | G4 — insurance | Новый check или поле |
| **P1** | G5 — bring-down / closing reps | Поле или новый check |
| **P1** | G6 — disclosure schedule mechanism | Поле |
| P2 | G7–G16 | 4 поля + расширения + новый check |
| P3 | G17–G26 | DEFER |

**Минимум для полноты группы:**
- 3 новых check'а P1: `rw_capitalization_and_subsidiaries`, `rw_real_property_and_leases`, `rw_environmental`.
- 3 поля P1: `has_insurance_reps`, `has_bring_down_mechanism`, `has_disclosure_schedule_mechanism`.
- 4 поля P2: `has_sandbagging_clause`, `has_materiality_scrape`, `has_rpt_reps` + расширение employee benefits.

**Общая оценка:** группа покрывает базовый M&A reps-контур (фундаментальные, финансовые / операционные, специальные reps, MAC/MAE), но пропускает критичные M&A-конструкции: capitalization / subsidiaries (ядро share deal), environmental, real property, insurance, bring-down, disclosure schedule mechanism, sandbagging, materiality scrape, interim covenants, RPT reps. Для доведения до ~85% требуется минимум 3 новых check'а + 7 новых полей.


## Группа: term

**Директория:** `playbooks/global_checks/term/`
**Дата анализа:** 2026-09-25
**Проверено checks:** 4 из 4
**Статус группы:** покрытие ~60% — покрыты срок/пролонгация, основания расторжения, последствия расторжения, форс-мажор. Отсутствуют: suspension as remedy, effective date / conditions precedent, общий survival clause, детальный exit-план, rescission vs termination, экономика termination payments, FM-notice procedure.

### 1. Что покрыто

| # | Check | Что покрывает |
|---|---|---|
| 1 | `force_majeure` | FM-оговорка: классические события (стихия, война, госакты), современные риски (пандемии, санкции, кибер), экономические основания, охват платежей, право расторжения при длительном FM, порог, бенефициар |
| 2 | `term_and_renewal` | Срок действия: тип (fixed / indefinite / by_event), начальный срок, автоматическая пролонгация, период, количество пролонгаций, срок / форма уведомления об отказе, сложность отказа |
| 3 | `termination_consequences` | Последствия расторжения: судьба авансов / минимальных платежей, early termination fee, переходный период и длительность, обработка данных, судьба IP / лицензий, конфиденциальность после расторжения |
| 4 | `termination_grounds` | Основания расторжения: for cause, cure period, for convenience, CoC, insolvency, sanctions / law change, баланс прав |

**Что это даёт в сумме:** покрыты 4 базовых механизма term-контура.

### 2. Что НЕ покрыто — пробелы

#### 🔴 P1 — высокий приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G1 | **Suspension as remedy for breach** — право приостановить исполнение при нарушении (между default и termination) | ст. 328, 719 ГК РФ | Поле `has_suspension_right` в `termination_grounds` или новый check |
| G2 | **Effective date / conditions precedent** — отложенное вступление в силу после CP | ст. 425, 432 ГК РФ; практика M&A | Поле `has_effective_date_conditions` в `term_and_renewal` |
| G3 | **Общий survival clause** — сохранение силы положений (indemnity, reps, dispute, IP, notices) | Договорная практика | Поле `survival_clause_summary` или новый check |
| G4 | **Termination payment economics / make-whole** — cap, расчёт (NPV, потерянная прибыль), порядок выплаты | Договорная практика | Расширить `termination_consequences`: `termination_payment_structure`, `termination_payment_cap` |
| G5 | **Detailed exit management / disengagement** — cooperation, knowledge transfer, handover, cutover | ISO 27001 A.15.2; практика | Поле `has_detailed_exit_plan` в `termination_consequences` |
| G6 | **Rescission vs termination** — отказ от договора (ст. 450.1 ГК РФ) с обратной силой | ст. 450.1 ГК РФ | Поле `has_rescission_right` в `termination_grounds` |
| G7 | **FM notice procedure** — форма, срок, содержание уведомления, сертификация (ТПП) | ст. 401 ГК РФ; практика | Поле `fm_notification_procedure` в `force_majeure` |
| G8 | **Change of law / illegality как отдельное основание** — не смешано с санкциями | ст. 401 п. 3, ст. 417 ГК РФ | Расщепить `on_sanctions_or_law_change` |

#### 🟡 P2 — средний приоритет

| ID | Риск | Норма | Что нужно |
|---|---|---|---|
| G9 | Termination fee / reverse termination fee (M&A) | Практика M&A | Поле `has_termination_fee` |
| G10 | Outside date / long-stop date | Практика M&A | Поле `has_outside_date` |
| G11 | Step-in / substitution rights | Basel; практика | Поле `has_step_in_right` |
| G12 | Partial impossibility / frustration | ст. 416, 417 ГК РФ | Поле `has_partial_impossibility` |
| G13 | Termination by mutual agreement | ст. 450 п. 1 ГК РФ | Поле `has_mutual_termination` |
| G14 | Renegotiation right on renewal | Договорная практика | Поле `has_renewal_renegotiation` |
| G15 | Claw-back / retroactive termination | Договорная практика | Поле `has_claw_back` |
| G16 | Regulatory cessation — прекращение по требованию регулятора | Отраслевые законы | Поле `has_regulatory_cessation` |
| G17 | Notice of termination — форма, срок, орган | Договорная практика | Поле `termination_notice_form` |
| G18 | Survival of specific obligations (возврат материалов, неразглашение, неконкуренция) | Договорная практика | Расширить `termination_consequences` |
| G19 | Continuing obligations during FM | Договорная практика | Поле `continuing_obligations_during_fm` |

#### 🟢 P3 — низкий приоритет / backlog

| ID | Риск | Что нужно |
|---|---|---|
| G20 | Notification of FM to insurers / TPP | Поле `fm_certification_required` |
| G21 | Cross-border tax on termination payments | Cross-ref с tax |
| G22 | Multi-party termination mechanics | Поле для multi-party |
| G23 | Termination in JV / consortium | Отдельный домен |
| G24 | Contractor termination obligations to third parties | Поле |
| G25 | Wind-down of captive insurance / parent guarantees | Специализированное |
| G26 | Surviving obligations of guarantors | Cross-ref с `finance/security` |
| G27 | Termination mechanics for open-source / API | Cross-ref с `ip_it` |

### 3. Cross-references (покрыто вне группы)

| Риск | Где покрыто |
|---|---|
| Расторжение при CoC | `coc/*` — частично ✅ |
| Расторжение при санкциях | `sanctions/sanctions_clauses` ✅ |
| Расторжение при дефолте по финансам | `liability/cross_default_and_acceleration` — частично ✅ |
| Уступка → последствия расторжения | `assignment_transfer/*` — частично ✅ |
| Ответственность после расторжения | `liability/*` — частично ✅ |
| IP-лицензии после расторжения | `ip_it/ip_license_scope_and_usage` — частично ✅ |
| Доступ к ИТ-системам и экспорт данных при расторжении | `ip_it/it_systems_access_and_data_export` — **дублирует часть `termination_consequences`** |
| HR-переход сотрудников при расторжении | `hr/*` — частично ✅ |

### 4. Вне scope global

- Отраслевое прекращение (bank resolution, insurance, energy curtailment)
- Franchise / distribution network termination
- Employment-transfer termination (TUPE, ст. 75 ТК РФ)
- Termination of regulated public contracts
- Bank resolution regimes (BRRD, FDIC)
- Aviation / shipping leases termination
- Long-term PPAs / offtake termination

### 5. Структурные проблемы группы

- ⚠️ **`termination_consequences` дублирует `ip_it/it_systems_access_and_data_export`** — требуется разграничение в `description` или вынос ИТ-части. → CONSIDER.
- ⚠️ **`on_sanctions_or_law_change` смешивает санкции и change of law.** → CONSIDER — расщепить.
- ⚠️ **`termination_grounds` перекрывается с `liability/cross_default_and_acceleration`** — право расторжения при финансовом дефолте. → CONSIDER.
- ⚠️ **`retrieval_profile` reuse:** `termination_check` в 2 checks, `force_majeure_check` и `term_and_renewal_check` — по одному. → CONSIDER.
- ⚠️ **Mismatch `severity_if_fail ≠ severity`** в `force_majeure` и `term_and_renewal` — осознанно. → CONSIDER as designed.
- ⚠️ **Порядок `<context>` до `<context_rules>`** во всех 4. → CONSIDER.
- ⚠️ **Дубли в nested `keywords`** во всех 4 (5–10 пар). → CONSIDER.
- ⚠️ **`description` ↔ `<role>`** во всех 4. → CONSIDER.
- ⚠️ **Дубли в `preferred_unit_types` (FM) и `enrichment_hints.preferred_clause_functions` (term_and_renewal).** → CONSIDER.
- ⚠️ **Отсутствие взаимных cross-refs между checks группы.** → DEFER.

### 6. Итоговые рекомендации

| Приоритет | Действие | Формат |
|---|---|---|
| **P1** | G1 — suspension as remedy | Поле или новый check |
| **P1** | G2 — effective date / CP | Поле |
| **P1** | G3 — survival clause | Поле или новый check |
| **P1** | G4 — termination payment economics | Расширить |
| **P1** | G5 — exit management | Поле |
| **P1** | G6 — rescission | Поле |
| **P1** | G7 — FM notice procedure | Поле |
| **P1** | G8 — change of law | Расщепить поле |
| P2 | G9–G19 | Поля + расширения |
| P3 | G20–G27 | DEFER |

**Минимум для полноты группы:**
- 2 новых check'а P1: `suspension_and_remedies`, `survival_and_exit_management`.
- 5 новых полей P1: `has_effective_date_conditions`, `termination_payment_structure` + `termination_payment_cap`, `has_rescission_right`, `fm_notification_procedure`.
- 1 расщепление: `on_sanctions_or_law_change`.
- 5–7 полей P2.

**Общая оценка:** группа покрывает базовый term-контур, хорошо согласована внутри. Пропускает: suspension as remedy, effective date / CP, общий survival, экономика termination payments, exit management, rescission, FM-notice procedure, change of law как отдельное основание. Также имеет структурные пересечения с `ip_it/it_systems_access_and_data_export`, `liability/cross_default_and_acceleration`, `sanctions/sanctions_clauses`. Для доведения до ~85% требуется минимум 2 новых check'а + 5–8 новых полей + 1 расщепление.



