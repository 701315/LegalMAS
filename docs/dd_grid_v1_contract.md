# DD Grid V1 — API Contract

## Endpoint

```
GET /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
```

**Auth:** `viewer` / `editor` / `admin` role in project.

**Response:** `DDGridV1ResponseDTO`

---

## Response Structure

```json
{
  "deal_id": "uuid",
  "run_id": "uuid",
  "global_groups": [...],
  "doc_type_classes": [...],
  "column_registry": { "column_id": "ColumnDTO" },
  "cell_values": { "doc_id": { "column_id": "CellValueDTO" } },
  "drawer_contents": { "doc_id": { "check_id": "DrawerDTO" } },
  "documents_meta": [...]
}
```

### Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `deal_id` | string UUID | Сделка |
| `run_id` | string UUID | Ран |
| `global_groups` | array | Иерархия глобальных проверок |
| `doc_type_classes` | array | Иерархия по типам документов |
| `column_registry` | dict | Все runtime-колонки |
| `cell_values` | dict | Значения ячеек: `{doc_id: {column_id: cell}}` |
| `drawer_contents` | dict | Drawer: `{doc_id: {check_id: drawer}}` |
| `documents_meta` | array | Метаданные документов |

---

## Hierarchy

### Global Groups

```
global_groups[]
  └── group_id, label, display_order
      └── checks[]
          └── check_id, check_name, display_order
              └── columns[]
                  └── column_id, label, format, display_order
```

**Сортировка:** groups по `display_order` → `label`;
checks внутри group по `display_order` → `name`.

### Doc-Type Classes

```
doc_type_classes[]
  └── group_id, label, display_order
      └── types[]
          └── type_code, name
              └── checks[]
                  └── (same as global)
```

**Скрытие:** doc-type class не включается, если ни один документ в run
не принадлежит этому типу.

---

## Column Registry

Каждая колонка описывает **один столбец** в DD Grid.

```json
{
  "column_id": "governing_law_and_forum__governing_law",
  "check_id": "governing_law_and_forum",
  "label": "Применимое право",
  "format": "text",
  "fallback_display": "—",
  "display_order": 10,
  "enum_labels": {},
  "unit": null
}
```

### `column_id` Format

```
{check_id}__{field_key}
```

### Column Formats

| Format | Rendering | Display when defined |
|---|---|---|
| `text` | Plain string | `str(raw_value)` + `unit` если задан |
| `enum` | Lookup label | `enum_labels[raw_value]` или raw если нет в словаре |
| `yes_no` | Boolean | `"Да"` / `"Нет"` |
| `presence_only` | Presence indicator | `"Присутствует"` |

---

## Cell Values

```json
{
  "cell_state": "defined",
  "display_value": "РФ",
  "raw_value": "РФ",
  "location_clause_ref": "п. 22",
  "location_page": 40,
  "location_confidence": "high",
  "has_location_fallback": false,
  "location_fallback_reason": null
}
```

### Cell States

| State | Meaning | Display |
|---|---|---|
| `defined` | Значение найдено | Formatted value |
| `not_defined` | Check выполнен, значение не найдено | `column.fallback_display` (обычно `"—"`) |
| `not_applicable` | Check не применим к этому doc_type | `"н/о"` |
| `not_executed` | Check не выполнялся для документа | `column.fallback_display` |
| `error` | Техническая ошибка выполнения | `"⚠ Ошибка"` |

### Cell State Priority (resolution order)

```
1. not_applicable  →  check.doc_types не пуст И doc_type не в списке
2. not_executed    →  нет CheckResult для (doc, check)
3. error           →  execution_status ∈ {FAILED, TIMEOUT, COMPUTE_FAILED, PERSIST_FAILED}
4. not_defined     →  value отсутствует / status_field = missing
5. defined         →  значение присутствует
```

### Display Value Rules

| Cell State | Display Value |
|---|---|
| `defined` | Форматированное значение по `column.format` |
| `not_defined` | `column.fallback_display` (default: `"—"`) |
| `not_executed` | `column.fallback_display` |
| `not_applicable` | `"н/о"` |
| `error` | `"⚠ Ошибка"` |

---

## Location Contract

Каждая ячейка может содержать location данные.

### Exact Location

```json
{
  "location_clause_ref": "п. 22",
  "location_page": 40,
  "location_confidence": "high",
  "has_location_fallback": false,
  "location_fallback_reason": null
}
```

**Семантика:** LLM точно указал clause_ref и page.
Фронт может показать pinpoint navigation.

### Fallback Location (без pinpoint)

```json
{
  "location_clause_ref": null,
  "location_page": null,
  "location_confidence": "low",
  "has_location_fallback": true,
  "location_fallback_reason": "LLM не указал точную ссылку для поля"
}
```

**Семантика:** LLM не указал точную ссылку.
`clause_ref` и `page` = null. Navigation недоступна.

### Fallback с check-level ref

```json
{
  "location_clause_ref": "main_contract:12.1",
  "location_page": 9,
  "location_confidence": "low",
  "has_location_fallback": true,
  "location_fallback_reason": "LLM не указал точную ссылку для поля"
}
```

**Семантика:** Ref/page взяты из check-level fallback (не из LLM per-field extraction).
Navigation приблизительная.

### Frontend Decision Table

| `has_location_fallback` | `clause_ref` / `page` | UI Action |
|---|---|---|
| `false` | заполнены | exact pinpoint → show link |
| `true` | заполнены | approximate → show with caveat |
| `true` | null / null | no navigation → hide location UI |
| `false` | null / null | no location → hide location UI |

---

## Drawer Contents

Drawer показывается при клике на ячейку / строку.

```json
{
  "check_id": "governing_law_and_forum",
  "check_name": "Применимое право и юрисдикция",
  "document_id": "uuid",
  "cell_state": "defined",
  "reason": "Применимое право указано как РФ...",
  "review_status": "no_issue_detected",
  "review_message": null,
  "display_text": "...",
  "execution_status": "SUCCESS",
  "fields": [...],
  "evidence_items": []
}
```

### Drawer Reason Precedence

```
1. metadata field "reason"       (из structured_data extraction)
2. metadata field "explanation"  (из structured_data extraction)
3. metadata field "notes"        (из structured_data extraction)
4. review_message                (из CheckResult)
5. display_text                  (из CheckResult)
```

Reason-like поля **не** дублируются в `evidence_items`.

### Drawer Fields

```json
{
  "column_id": "governing_law_and_forum__governing_law",
  "field_name": "governing_law_value",
  "label": "Применимое право",
  "cell_state": "defined",
  "display_value": "РФ",
  "raw_value": "РФ",
  "location_clause_ref": "п. 22",
  "location_page": 40,
  "location_confidence": "high",
  "has_location_fallback": false,
  "location_fallback_reason": null
}
```

### Evidence Items

```json
{
  "evidence_items": ["п. 1.1", "п. 2.4"]
}
```

Извлекаются из `EVIDENCE_LIST` полей extraction metadata.
`reason` / `explanation` / `notes` **не** попадают в `evidence_items`.

### `cell_state` в Drawer

Сводный cell_state по всем columns check (worst case priority):

```
error > defined > not_defined > not_executed > not_applicable
```

---

## Documents Meta

```json
{
  "document_id": "uuid",
  "filename": "contract.pdf",
  "doc_type": "contract_1.6_real_estate",
  "status": "enriched",
  "folder_path": "01. Legal"
}
```

Отсортированы по `filename` (case-insensitive), затем по `document_id`.

---

## Minimal Example (anonymized)

```json
{
  "deal_id": "aaaaaaaa-0000-0000-0000-000000000001",
  "run_id":  "bbbbbbbb-0000-0000-0000-000000000001",
  "global_groups": [
    {
      "group_id": "Governing law",
      "label": "Governing Law",
      "display_order": 0,
      "checks": [
        {
          "check_id": "governing_law_and_forum",
          "check_name": "Применимое право и юрисдикция",
          "display_order": 0,
          "columns": [
            {
              "column_id": "governing_law_and_forum__governing_law",
              "check_id": "governing_law_and_forum",
              "label": "Применимое право",
              "format": "text",
              "fallback_display": "—",
              "display_order": 10,
              "enum_labels": {},
              "unit": null
            }
          ],
          "display_summary_field": null,
          "metadata_fields": ["reason"]
        }
      ]
    }
  ],
  "doc_type_classes": [],
  "column_registry": {
    "governing_law_and_forum__governing_law": {
      "column_id": "governing_law_and_forum__governing_law",
      "check_id": "governing_law_and_forum",
      "label": "Применимое право",
      "format": "text",
      "fallback_display": "—",
      "display_order": 10,
      "enum_labels": {},
      "unit": null
    }
  },
  "cell_values": {
    "doc-00000001": {
      "governing_law_and_forum__governing_law": {
        "cell_state": "defined",
        "display_value": "РФ",
        "raw_value": "РФ",
        "location_clause_ref": "п. 22",
        "location_page": 40,
        "location_confidence": "high",
        "has_location_fallback": false,
        "location_fallback_reason": null
      }
    }
  },
  "drawer_contents": {
    "doc-00000001": {
      "governing_law_and_forum": {
        "check_id": "governing_law_and_forum",
        "check_name": "Применимое право и юрисдикция",
        "document_id": "doc-00000001",
        "cell_state": "defined",
        "reason": "Применимое право: Российская Федерация.",
        "review_status": "no_issue_detected",
        "review_message": null,
        "display_text": "Применимое право: РФ.",
        "execution_status": "SUCCESS",
        "fields": [
          {
            "column_id": "governing_law_and_forum__governing_law",
            "field_name": "governing_law_value",
            "label": "Применимое право",
            "cell_state": "defined",
            "display_value": "РФ",
            "raw_value": "РФ",
            "location_clause_ref": "п. 22",
            "location_page": 40,
            "location_confidence": "high",
            "has_location_fallback": false,
            "location_fallback_reason": null
          }
        ],
        "evidence_items": []
      }
    }
  },
  "documents_meta": [
    {
      "document_id": "doc-00000001",
      "filename": "contract.pdf",
      "doc_type": "contract_1.6_real_estate",
      "status": "enriched",
      "folder_path": null
    }
  ]
}
```



