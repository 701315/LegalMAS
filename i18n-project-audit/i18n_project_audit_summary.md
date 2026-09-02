# I18n Project Audit

Дата: 2026-09-02T11:47:25.041211+00:00
Корень проекта: `/srv/steloom-dev`
Папка отчётов: `/srv/steloom-dev/i18n-project-audit`

## Масштаб

- Просканировано файлов: **940**
- Пропущено крупных файлов (> 2 MB): **0**
- Найдено кандидатов: **6025**
- Высокий приоритет: **1981**
- Средний приоритет: **3975**
- Исключено как логи, тесты или технические строки: **69**

## По потокам

- Frontend UI: **3378**
- Backend user-facing: **455**
- Email и exports: **212**
- Backend internal: **1755**
- Контент, fixtures, документация: **225**

## Технологии

- **frontend_framework:** react, vite
- **frontend_routing:** react-router-dom
- **frontend_ui:** tailwindcss

## Ограничения

- Скрипт не сканирует собственную output-папку.
- Файлы больше 2 MB намеренно пропускаются, чтобы не анализировать generated data, dumps и крупные fixtures.
- На одном файле анализ ограничен 500 кандидатами.
- Многострочные JavaScript/Python literals могут требовать отдельной ручной проверки или AST-аудита.

## Первые задачи

- **15x**, `frontend_ui`, `frontend/src/components/ConfirmDialog.tsx:26` — «Отмена»
- **10x**, `frontend_ui`, `frontend/src/components/deals/RunLaunchDrawer.tsx:78` — «Запуск анализа»
- **10x**, `frontend_ui`, `frontend/src/components/new-project/FlowSummary.tsx:109` — «Документы»
- **9x**, `frontend_ui`, `frontend/src/components/documents/DocumentChunksModal.tsx:106` — «Закрыть»
- **9x**, `frontend_ui`, `frontend/src/components/ui/ConfirmDialog.tsx:50` — «Да»
- **8x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:70` — «Документ»
- **8x**, `frontend_ui`, `frontend/src/components/documents/DocumentDetails.tsx:399` — «Тип документа»
- **8x**, `frontend_ui`, `frontend/src/components/new-project/flowInstructions.ts:64` — «Проект»
- **8x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:27` — «Внутренний аудит»
- **8x**, `frontend_ui`, `frontend/src/marketing/components/platform/content/platformContent.ts:42` — «Запросить демонстрацию»
- **7x**, `frontend_ui`, `frontend/src/components/layout/AppShell.tsx:178` — «Инструкции»
- **7x**, `frontend_ui`, `frontend/src/marketing/content/siteNav.ts:27` — «Сценарии использования»
- **7x**, `frontend_ui`, `frontend/src/pages/AdminPage.tsx:149` — «Поиск…»
- **7x**, `frontend_ui`, `frontend/src/pages/DealListPage.tsx:130` — «Все»
- **7x**, `frontend_ui`, `frontend/src/pages/tabs/dd-grid-v1/DDGridV1List.tsx:672` — «Документ»
- **6x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:73` — «Проверка»
- **6x**, `frontend_ui`, `frontend/src/components/documents/DocumentDetails.tsx:402` — «Язык»
- **6x**, `frontend_ui`, `frontend/src/components/requests/RequestSidePanel.tsx:271` — «Скопировано»
- **6x**, `frontend_ui`, `frontend/src/marketing/components/home/ApplicationSection/ApplicationSection.tsx:17` — «Анализ договоров»
- **6x**, `frontend_ui`, `frontend/src/pages/AdminPage.tsx:175` — «Очистить поиск»
- **5x**, `backend_user_facing`, `src/services/pipeline_view/stage_structure.py:129` — «STRUCTURE: дерево документа»
- **5x**, `email_export`, `src/services/export/dd_grid_v1_excel_builder.py:242` — «Тип»
- **5x**, `frontend_ui`, `frontend/src/components/admin/TenantsTable.tsx:231` — «Проекты»
- **5x**, `frontend_ui`, `frontend/src/components/instructions/DraftEditForm.tsx:319` — «Редактор»
- **5x**, `frontend_ui`, `frontend/src/components/instructions/GlobalInstructionEditor.tsx:445` — «Название»
- **5x**, `frontend_ui`, `frontend/src/components/new-project/FlowSummary.tsx:121` — «Профиль модели»
- **5x**, `frontend_ui`, `frontend/src/components/requests/RequestSidePanel.tsx:22` — «Высокий»
- **5x**, `frontend_ui`, `frontend/src/components/requests/RequestSidePanel.tsx:23` — «Средний»
- **5x**, `frontend_ui`, `frontend/src/components/requests/RequestSidePanel.tsx:156` — «Статус»
- **5x**, `frontend_ui`, `frontend/src/components/requests/RequestSidePanel.tsx:297` — «Сохранить»
