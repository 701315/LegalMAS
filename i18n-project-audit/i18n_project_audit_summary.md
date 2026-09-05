# I18n Project Audit

Дата: 2026-09-04T18:58:15.040500+00:00
Корень проекта: `/srv/steloom-dev`
Папка отчётов: `/srv/steloom-dev/i18n-project-audit`

## Масштаб

- Просканировано файлов: **985**
- Пропущено крупных файлов (> 2 MB): **0**
- Найдено кандидатов: **6627**
- Высокий приоритет: **625**
- Средний приоритет: **2693**
- Исключено как логи, тесты или технические строки: **3309**

## По потокам

- Frontend UI: **892**
- Backend user-facing: **433**
- Email и exports: **78**
- Backend internal: **1759**
- Контент, fixtures, документация: **3465**

## Технологии

- **frontend_framework:** react, vite
- **frontend_i18n:** i18next, react-i18next
- **frontend_routing:** react-router-dom
- **frontend_ui:** tailwindcss

## Ограничения

- Скрипт не сканирует собственную output-папку.
- Файлы больше 2 MB намеренно пропускаются, чтобы не анализировать generated data, dumps и крупные fixtures.
- На одном файле анализ ограничен 500 кандидатами.
- Многострочные JavaScript/Python literals могут требовать отдельной ручной проверки или AST-аудита.

## Первые задачи

- **8x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:27` — «Внутренний аудит»
- **8x**, `frontend_ui`, `frontend/src/marketing/components/platform/content/platformContent.ts:42` — «Запросить демонстрацию»
- **7x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:27` — «Сценарии использования»
- **6x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:17` — «Анализ договоров»
- **5x**, `backend_user_facing`, `src/services/pipeline_view/stage_structure.py:129` — «STRUCTURE: дерево документа»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_extract.py:33` — «EXTRACT: layout после извлечения»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_primary.py:33` — «PRIMARY: одноязычный source»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_source.py:33` — «SOURCE: исходный документ»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:12` — «M&A и Due Diligence»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:22` — «Комплаенс и контроль»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/shared/MarketingPageHeader.tsx:14` — «Запросить демо»
- **4x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:71` — «Юридические фирмы»
- **3x**, `email_export`, `src/services/export/dd_request_loader.py:117` — «addressee": "Юридический советник»
- **3x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:157` — «Сценарий использования»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/landingContent.ts:162` — «Выводы с привязкой к источнику»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:76` — «Корпоративные юристы»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:89` — «Расширенный анализ»
- **3x**, `frontend_ui`, `frontend/src/marketing/pages/solutions/AuditCompliancePage.tsx:191` — «Аудиторский след»
- **3x**, `frontend_ui`, `frontend/src/marketing/pages/solutions/AuditCompliancePage.tsx:246` — «Структурирование массива»
- **3x**, `frontend_ui`, `frontend/src/marketing/pages/solutions/CompliancePage.tsx:263` — «и не выдает непрозрачные ответы»
- **2x**, `backend_user_facing`, `src/api/endpoints/global_instruction_versions.py:508` — «ID версии для сравнения»
- **2x**, `backend_user_facing`, `src/api/endpoints/tenant_admin.py:978` — «Только для superadmin: посмотреть конкретный tenant»
- **2x**, `backend_user_facing`, `src/api/schemas/playbooks.py:78` — «Профиль глубины проверки: core/full/quick и т.п.»
- **2x**, `email_export`, `src/services/export/report_builder.py:67` — «""Подсчитать severity counts напрямую из check_results.»
- **2x**, `email_export`, `src/services/export/report_builder.py:84` — «""Подсчитать conditional checks статистику.»
- **2x**, `email_export`, `src/services/export/report_builder.py:137` — «""Подсчитать метрики качества анализа.»
- **2x**, `email_export`, `src/workers/export_pending.py:65` — «ожидающей»
- **2x**, `frontend_ui`, `frontend/src/marketing/components/home/KnowledgeGrowthSection/contract-texts.ts:16` — «Договор»
- **2x**, `frontend_ui`, `frontend/src/marketing/components/platform/content/platformContent.ts:78` — «Что это даёт юристу»
- **2x**, `frontend_ui`, `frontend/src/marketing/components/shared/MarketingPageFooter.tsx:42` — «Steloom — главная»
