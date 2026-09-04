# I18n Project Audit

Дата: 2026-09-04T07:11:23.942952+00:00
Корень проекта: `/srv/steloom-dev`
Папка отчётов: `/srv/steloom-dev/i18n-project-audit`

## Масштаб

- Просканировано файлов: **982**
- Пропущено крупных файлов (> 2 MB): **0**
- Найдено кандидатов: **6837**
- Высокий приоритет: **799**
- Средний приоритет: **2906**
- Исключено как логи, тесты или технические строки: **3132**

## По потокам

- Frontend UI: **1103**
- Backend user-facing: **455**
- Email и exports: **212**
- Backend internal: **1779**
- Контент, fixtures, документация: **3288**

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

- **8x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:70` — «Документ»
- **8x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:27` — «Внутренний аудит»
- **8x**, `frontend_ui`, `frontend/src/marketing/components/platform/content/platformContent.ts:42` — «Запросить демонстрацию»
- **7x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:27` — «Сценарии использования»
- **6x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:73` — «Проверка»
- **6x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:17` — «Анализ договоров»
- **5x**, `backend_user_facing`, `src/services/pipeline_view/stage_structure.py:129` — «STRUCTURE: дерево документа»
- **5x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:242` — «Тип»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_extract.py:33` — «EXTRACT: layout после извлечения»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_primary.py:33` — «PRIMARY: одноязычный source»
- **4x**, `backend_user_facing`, `src/services/pipeline_view/stage_source.py:33` — «SOURCE: исходный документ»
- **4x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:72` — «Тип документа»
- **4x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:77` — «Стр.»
- **4x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:78` — «Пункт»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:12` — «M&A и Due Diligence»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:22` — «Комплаенс и контроль»
- **4x**, `frontend_ui`, `frontend/src/marketing/components/shared/MarketingPageHeader.tsx:14` — «Запросить демо»
- **4x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:71` — «Юридические фирмы»
- **3x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:76` — «Значение»
- **3x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:359` — «Режим проверок: {checks_mode}»
- **3x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:361` — «Стратегия пайплайна: {pipeline_strategy}»
- **3x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:456` — «Документов»
- **3x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:553` — «Триггер»
- **3x**, `email_export`, `src/services/export/dd_request_loader.py:53` — «addressee": "Юридический советник»
- **3x**, `frontend_ui`, `frontend/index.html:9` — «Steloom — DD grid и анализ документов для юристов»
- **3x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:157` — «Сценарий использования»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/landingContent.ts:162` — «Выводы с привязкой к источнику»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/landingContent.ts:223` — «Проверка»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:76` — «Корпоративные юристы»
- **3x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:89` — «Расширенный анализ»
