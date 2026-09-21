# PLAN: Detection Audit + Anchor Refactoring

**Source:** полный план согласован в диалоге, v2.0 (consolidated)
**Started:** 2026-09-21

## Track B: Anchor & Location

| Этап | Статус | Commit | Tag | Notes |
|---|---|---|---|---|
| B0.1 — sized-chunks clause_uids/raw_uids | ✅ DONE | a1a3f0d | pre-B0.1-20260921-042922 / post-B0.1-20260921-043501 | Merge: e05acb7..64e1b57 |
| B0.2 — element_id (layout UUID) + chunk_id (canonical) | ⏳ TODO | — | — | Merged from old B0.2+B0.3 |
| B0.2b — DD Grid LOCATION → viewer page mismatch | ⏳ TODO | — | — | Клик на p. 4 · cl. 7.2 открыл page 1 с подсветкой cl. 1.1. Frontend-баг в передаче payload или useEffect modal. Требует аудита frontend DD Grid + DocumentViewerModal |
| B0.3 — CheckResult.bbox from layout | ⏳ TODO | — | — | Renumbered from old B0.4 |
| B0.4 — context_trace.score_breakdown | ⏳ TODO | — | — | Renumbered from old B0.5 |
| B2 — Citation Resolver | ⏳ TODO | — | — | — |
| B3 — Citation Extraction | ⏳ TODO | — | — | — |
| B4 — Persistence Layer | ⏳ TODO | — | — | — |
| B5 — API + Frontend | ⏳ TODO | — | — | — |

## Track A: Detection Quality Audit

| Этап | Статус | Notes |
|---|---|---|
| A1 — Программный аудит (SQL) | ⏳ TODO | — |
| A2 — Ручной аудит (юрист) | ⏳ TODO | требует юриста |
| A3 — Аудит YAML | ⏳ TODO | требует юриста |
| A4 — Калибровка порогов | ⏳ TODO | — |
| A5 — Улучшение промптов | ⏳ TODO | — |

## Process Rules

Каждый фикс:

1. Pre-tag на `origin/master` (формат: `pre-B0.N-YYYYMMDD-HHMMSS`).
2. Ветка `fix/B0.N-краткое-описание`.
3. Атомарный commit с Conventional Commits message.
4. Push ветки в origin.
5. Тесты (dedicated + regression).
6. Merge `--no-ff` в master.
7. Post-tag (формат: `post-B0.N-YYYYMMDD-HHMMSS`).
8. Удаление ветки локально и на GitHub.
9. Обновление таблицы в этом файле.

При падении тестов: `git reset --hard <pre-tag>`, `git push --force-with-lease`.

## References

- Полный план v2.0 — в истории диалогов (передавать как контекст в новый диалог).
- `docs/adr/` — ADR по проектным решениям.
- `docs/dd_grid_v1_contract.md` — контракт DD Grid.

## Process Rules — Worker Restart

**Критично:** при изменении кода, который выполняется внутри Celery workers,
необходим **перезапуск соответствующего worker'а** перед тестами.
Backend `uvicorn --reload` покрывает только `src/api/**`, не worker'ы.

### Маппинг: код → worker

| Изменённый код | Worker для перезапуска |
|---|---|
| `src/api/**` | backend (uvicorn --reload, авто) |
| `src/engine/checks/**` | **worker-heavy-checks** |
| `src/engine/detectors/**` | **worker-heavy-checks** |
| `src/engine/retrieval/**` | **worker-heavy-checks** |
| `src/engine/content/**` | worker-heavy-enrichment + worker-heavy-checks |
| `src/workers/**`, `src/services/**` | worker-default |
| `src/classifiers/**` | worker-heavy-segment-classification |

### Обязательная проверка перед новым run'ом

```bash
git log --oneline -1
ps -o pid,lstart,cmd -p $(pgrep -f 'worker-heavy-checks' | head -1)