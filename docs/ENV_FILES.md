# Frontend env files

| Файл | Назначение | Читает |
|------|-----------|--------|
| `.env` | Базовые значения | Vite всегда |
| `.env.local` | Локальные overrides (в .gitignore) | Vite в dev |
| `.env.development` | Dev-контур, проверяется audit | `audit_env_contract.py` |
| `.env.production` | Production сборка | Vite при build |

⚠️ Добавляя новую `VITE_*` переменную, обновляйте ОБА файла:
- `.env.development` (для dev аудита)
- `.env.production` в DEMO контуре (для prod)
