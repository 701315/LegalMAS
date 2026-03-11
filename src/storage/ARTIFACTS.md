## Путь артефактов в S3/MinIO

Все артефакты живут под префиксом:

- `tenants/{tenant_id}/deals/{deal_id}/...`

`tenant_id` и `deal_id` берём **только** из БД (Deal.tenant_id, Deal.id), никогда не подменяем и не берём из запроса.

### Документные артефакты (по document_id)

| Стадия           | Назначение                     | Путь в S3                                                           | Метод ArtifactPath                                   | Кто пишет                               |
|------------------|--------------------------------|---------------------------------------------------------------------|------------------------------------------------------|-----------------------------------------|
| original         | Оригинальный файл документа   | `tenants/{tenant_id}/deals/{deal_id}/originals/{document_id}`      | `original(tenant_id, deal_id, document_id)`          | `import_worker._async_import`          |
| layout_raw       | Raw layout (textlayoutraw)    | `tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/raw.json` | `layout_raw(tenant_id, deal_id, document_id)`        | `extract_worker._extract_document_async` |
| layout_sanitized | PII‑sanitized layout          | `tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/sanitized.json` | `layout_sanitized(tenant_id, deal_id, document_id)`  | `PIISanitizer.sanitize`                |
| clause_tree      | Структура документа (дерево)  | `tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/clause_tree.json` | `clause_tree(tenant_id, deal_id, document_id)`       | `structure_builder._build_structure_async` |
| pii_mapping      | Шифрованная карта PII‑токенов | `tenants/{tenant_id}/deals/{deal_id}/pii/{document_id}/mapping.enc` | `pii_mapping(tenant_id, deal_id, document_id)`       | `PIISanitizer.sanitize`                |

### Run‑артефакты (по run_id)

| Тип артефакта | Назначение                           | Путь в S3                                                                 | Метод ArtifactPath                                  | Кто пишет                   |
|---------------|--------------------------------------|---------------------------------------------------------------------------|-----------------------------------------------------|----------------------------|
| check_results | Результаты проверок (NDJSON)         | `tenants/{tenant_id}/deals/{deal_id}/results/{run_id}/check_results.jsonl` | `check_results(tenant_id, deal_id, run_id)`         | `runner._run_checks_async` |
| evidence      | Сниппеты‑evidence для проверок      | `tenants/{tenant_id}/deals/{deal_id}/results/{run_id}/evidence.jsonl`     | `evidence(tenant_id, deal_id, run_id)`              | `runner._run_checks_async` |

### Правила использования

- Любая новая стадия пайплайна **обязана** использовать `ArtifactPath.*` для построения путей.
- `tenant_id` и `deal_id`:
  - берём из БД (Deal, Document.deal), либо передаём из оркестратора;
  - не подменяем `tenant_id` на `deal_id`.
- В тасках Celery:
  - либо передаём только `document_id`/`run_id` и внутри достаём `tenant_id`/`deal_id` из БД;
  - либо явно пробрасываем `(tenant_id, deal_id)` из верхнего уровня (и документируем это).

