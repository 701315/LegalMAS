# Steloom / LegalMAS — Open Work (Недоделки)

**Date:** 2026-10-26
**Snapshot:** deployed HEAD `e1325f9` (18 commits over audited baseline `f22e3ba`)
**Status vs DD package:** 0 HIGH open, 51 risks documented (9 CLOSED, 42 open/accepted)
**Purpose:** Standalone TODO — что осталось, с effort estimates и приоритетом

---

## Executive summary

- **0 HIGH open** — все критичные закрыты: R-33 (concurrent runs), R-49 (model_configs auth), R-52 (rebuild race), R-03 (PII rate limit) — CLOSED с end-to-end evidence (E106)
- **Blocker для external test access:** none
- **Blocker для VC demo:** none
- **Highest-priority remaining:** R-50 (MEDIUM, Content-Disposition, ~30 min), R-53 (LOW, test gap, ~2–3 ч)
- **Owner decisions, not yet implemented:** R-01 (JWT revocation, ~8 ч), R-02 (audit gaps, ~6 ч), R-04 (PII reveal flag, ~4 ч) — ACCEPTED + PLANNED к первому платящему клиенту

**Recommended action:** ship VC demo на текущем состоянии (0 HIGH open, evidence полный). Начать с P1 quick-wins (~7 ч) до первого платящего клиента, остальное — post-round.

---

## Part 1: Что осталось по приоритетам

### P0 — Блокеры (нет)

**Пусто.** Все HIGH risks закрыты. Deploy `e1325f9` production-ready.

| Was HIGH | Status | Evidence |
|---|---|---|
| R-33 concurrent runs | ✅ CLOSED | Migration `bf78307e1293` + API 409 (curl verified, E106) |
| R-49 model_configs unauth | ✅ CLOSED | `require_superadmin` + frontend hide + 15/15 tests (E106) |
| R-52 rebuild race | ✅ CLOSED | Same fix as R-33 (E106) |
| R-03 PII reveal no rate limit | ✅ CLOSED | `check_pii_reveal_rate_limit` 10/min (E106) |

---

### P1 — Fix before first paying customer (HIGH-priority MEDIUM + ACCEPTED+PLANNED)

Owner decisions из §8 QUALITY_AND_RISKS.md, ещё не реализованы:

| ID | Severity | Item | Effort | Owner status |
|---|---|---|---|---|
| **R-01** | MEDIUM | JWT revocation — no invalidate on deactivation/demotion/password change | ~8 ч | ACCEPTED + PLANNED. План: `password_changed_at` + TTL 30min + refresh + re-issue |
| **R-02** | MEDIUM | Audit gaps — login, upload-id, download, admin-users не аудируются | ~6 ч | PARTIALLY ACCEPTED + PLANNED. 40+ write actions audited; gaps известны |
| **R-04** | MEDIUM | PII reveal `editor` без отдельного `can_reveal_pii` flag | ~4 ч | ACCEPTED + PLANNED. План: rate limit (✅ done в R-03) + flag + confirm dialog |
| **R-10** | MEDIUM | PII key rotation отсутствует | ~4 ч | OPEN. План: multi-key decrypt (current + previous) |
| **R-18** | MEDIUM | `_truncated` пишется backend, не показывается frontend → partial value выглядит как complete | ~3 ч | OPEN. План: badge в `DDGridV1Drawer` + `DDGridV1Matrix` |
| **R-22** | MEDIUM | CI = только `pip-audit`; нет pytest/ruff/bandit workflow | ~2 ч | OPEN. План: `.github/workflows/smoke.yml` (ruff + pytest security/api) |
| **R-27** | MEDIUM | `dd_grid_v1_contract.md` stale (не отражает `cell_risk_level`, `top_risk_*`, actual execution_status) | ~2 ч | OPEN. План: update contract doc |
| **R-32** | MEDIUM | LLM alerts sleeping — нет worker `/metrics` scrape endpoint | ~4 ч | OPEN. План: worker Prometheus endpoint + alert wiring |
| **R-50** | MEDIUM | Content-Disposition header injection в `documents/exports.py:196` (raw f-string, 3 endpoints) | ~30 мин | OPEN. План: extract `_build_content_disposition` из `pdf_urls.py` в shared util |

**Итого P1:** ~34 ч (~4.5 рабочих дня). Можно параллелить — R-50, R-27, R-22 — быстрые (< 2 ч), R-01/R-02/R-10/R-32 — по полдня.

---

### P2 — Post-round (quick wins, not urgent)

| ID | Severity | Item | Effort |
|---|---|---|---|
| R-05 | MEDIUM | Rate limiter no fallback если Redis down (login → 500 instead of 429) | ~1 ч |
| R-08 | LOW | `create_planned` — `IntegrityError` не пойман (LOW, есть partial indexes) | ~30 мин |
| R-13 | LOW-MEDIUM | PDF export `inline`; download not audited | ~1 ч |
| R-14 | LOW | No `password_changed_at` / `last_login_at` (часть R-01) | ~1 ч |
| R-23 | LOW-MEDIUM | Temp ZIP not cleaned on success (`deals/documents.py:222`) | ~30 мин |
| R-24 | LOW-MEDIUM | HEIC/WebP/HEIF magic not checked; magic fail → `unknown` (not QUARANTINE) | ~2 ч |
| R-26 | LOW | `prompts/README.md` пустой | ~30 мин |
| R-28 | LOW-MEDIUM | Нет rollback script для deploy | ~3 ч |
| R-31 | LOW-MEDIUM | `QualityGateError` → QUARANTINE, нет `LAYOUT_QUARANTINED` audit event | ~30 мин |
| R-34 | LOW-MEDIUM | Mode C chunk planner не alerted | ~30 мин |
| R-40 | LOW | `/storage/*` MinIO proxy exposed (bucket private, 403) | ~5 мин (remove from Caddyfile) |
| R-45 | LOW | `test_leakage_repro.py` fixture безусловно `DELETE FROM audit_logs` на `mas_dd` | ~1 ч |
| **R-53** | **LOW** | **Test gap: MagicMock не expires ORM, unit test не ловит MissingGreenlet; integration test нужен** | **~2–3 ч** |

**Итого P2:** ~13 ч (~1.5 рабочих дня). Можно делать инкрементально.

---

### P3 — Accepted / Won't fix (low priority or by design)

Не трогаем без явного запроса:

| ID | Severity | Причина accepted |
|---|---|---|
| R-11 | LOW | ROLE_MAP only RU/EN — opt-in, базовое покрытие |
| R-12 | LOW | `PERSONNAME1` collision — вероятность ~0 |
| R-15 | INFO | Pre-auth `tenant_id` из header — forensic confusion only |
| R-16 | INFO | Docstring "no role check" vs код — cosmetic |
| R-17 residual | LOW | Delimiter escape not sanitized — targeted attack only |
| R-19 | LOW-MEDIUM | Weak grounding 0.1–0.3 → extraction — anchor suppressed downstream |
| R-20 | LOW | Viewer bypasses frontend download — owner-intent |
| R-21 | LOW | `not_applicable` не localized — i18n cosmetic |
| R-25 | MEDIUM | `pass` + `clause_missing` — defensive code, owner-intent |
| R-29 | LOW | Dev defaults в коде (MINIO_SECRET_KEY, DATABASE_URL) — overridable через .env |
| R-30 | LOW | Только один ADR — incremental |
| R-33 rate limit `/run` | — | Отдельный слой к R-33 core (DB guard уже защищает) — можно добавить 5/hour per user |
| R-35 | LOW | Geometric sort fallback — silent ordering, low impact |
| R-36 | LOW | `AUDIT_FINAL` playbook-only — clarify в HANDOVER |
| R-37 | INFO | HANDOVER `d692e18` stale — already noted |
| R-41 | INFO | `/ws/*` dead block — hygiene |
| R-43 | LOW dormant | `anchor_uid` producer не найден — not activated |
| R-51 | LOW | `document_types.py` GET public — read-only metadata |

---

### P4 — Deferred from DD scope (UNKNOWN / not audited)

Не блокеры для VC (honest disclosure есть в README §Not covered), но надо знать:

**Structure pipeline (~70 files):**
- `_element_classifier/`, `_heading_builder/`, `_heading_scoring/`, `_hierarchy_builder/`, `_models/` (except `_identity.py`)
- `semantic_enrichment/`, `coherence/`, `cohesion/`
- `chunk_planner/_types.py`, `_clause_detector/routing.py`

**Alembic migrations:** 4 viewed of ~150 (initial, jobs unique, plan_items unique, schema_drift). Full history not audited — risk: unpredicted migration behavior на schema_drift recovery.

**Frontend:** только DD Grid V1. Marketing pages, admin/tenant, hooks/stores — не аудированы.

**Supply chain / CVE:**
- `pip-audit` **не запускался** на полный `requirements.txt`
- docling 2.121.0, PyMuPDF 1.28.2, pdfplumber 0.11.4 — версии pinned, но CVE-scan not run
- `office-converter/server.py` internal XML / macro handling — не audited deeply (LibreOffice `--safe-mode` отсутствует, но container isolated + non-root)

**Other:**
- `aws/` — not read
- `monitoring/` deep stack — только `alerts/*.yml`
- `docs/AUDIT_FINAL_2026-10-17.txt` — playbook-YAML only, not app audit

---

## Part 2: Инфраструктурные пробелы (не в risk register)

Это не код-риски, а **process/infra**, которые стоит закрыть отдельно:

| # | Пробел | Влияние | Effort |
|---|---|---|---|
| I-1 | **Test DB infrastructure отсутствует** — нет `TEST_DATABASE_URL`, integration tests (race, RLS, async rollback) негде запускать | R-53 — прямое следствие | ~1–2 дня (создать test DB + fixture cleanup) |
| I-2 | **CI workflow** — только `pip-audit`, нет pytest/ruff/bandit | R-22 — direct fix | ~2 ч (часть P1) |
| I-3 | **Pre-commit hooks** отсутствуют | Стиль/линт drift могут попадать в коммиты | ~30 мин |
| I-4 | **`pip-audit` на полный requirements** не запускался | Supply chain unknowns | ~30 мин |
| I-5 | **Rollback script** для deploy отсутствует | R-28 — прямое следствие | ~3 ч (часть P2) |
| I-6 | **Worker `/metrics` endpoint** отсутствует | R-32 — direct fix | ~4 ч (часть P1) |

---

## Part 3: Не реализованные owner decisions (§8 QUALITY_AND_RISKS.md)

Три решения owner 2026-10-26 — ACCEPTED + PLANNED, но в код **не внедрены**:

### Q3 → R-01: JWT revocation
**План (~8 ч):**
- Column `password_changed_at` в `users`
- Middleware: `token.iat < user.password_changed_at` → 401
- TTL снизить 8h → 30min + refresh endpoint (re-issue)
- Или: `token_version` в user + JWT claim, increment на password change / role change / deactivation

### Q4 → R-04: PII reveal flag
**План (~4 ч):**
- Column `can_reveal_pii` (bool, default false) в `deal_members`
- Rate limit — ✅ **уже done** (R-03, commit `56bb76d`)
- `require_project_role` для PII endpoint — дополнительно проверить `can_reveal_pii` flag
- Frontend: confirm dialog перед reveal
- Owner UI: включить флаг для editor'а

### Q5 → R-02: Audit gaps
**План (~6 ч):**
- Login events (успешный/неуспешный) → `audit_logs`
- Upload endpoint (сейчас только async import worker логирует `IMPORT`)
- Download export (сейчас lifecycle audited, download no)
- Admin user management (create/update/delete user)

---

## Part 4: Что уже сделано (контекст, чтобы не путаться)

**9 CLOSED risks** (E99–E106):
- R-03 PII rate limit — `56bb76d`
- R-07 PII key verified — E104
- R-33 concurrent runs — `cf315e4` + `fa092ed` + `e1325f9`
- R-38 demo meta — E103
- R-39 backup rotation — E103
- R-44 test fixture — E100
- R-46 Q6 persistent — `3bd6beb` + `763f2d9`
- R-49 model_configs auth — `061c7e3` + `524988b`
- R-52 rebuild race — `f46f6ec` + `e1325f9`

**Пофикшено в working tree → deployed at `e1325f9`:**
- Migration `bf78307e1293` — partial unique index (in demo DB)
- Migration `175b89560f5f` — merge (schema_drift recovery)
- 19 commits над baseline `f22e3ba`

**Evidence chain:**
- E99–E101: 134/134 pytest
- E102: E2E 17.5 min (baseline)
- E103: deploy hardening (Q6 persist + rotation + meta)
- E104: threat model v1.0
- E105: dev E2E 15.2 min (post-fix)
- E106: race 409 verified + MissingGreenlet fix + demo re-deploy

---

## Part 5: Рекомендация

### Для отправки tech VC (сейчас)
**Ship как есть.** 0 HIGH open, evidence полный (E99–E106), demo `e1325f9` production-ready. Honest disclosure: P4 unknowns + P1/P2/P3 documented в QUALITY_AND_RISKS.md §6.

### Перед первым платящим клиентом (~2–3 дня)
Закрыть **P1 HIGH-priority** (не все — выборочно):

**Must-fix до production:**
1. **R-01** (JWT revocation, ~8 ч) — без него уволенный сотрудник имеет доступ 8h
2. **R-50** (Content-Disposition, ~30 мин) — trivial fix
3. **R-04** (PII flag, ~4 ч) — compliance concern
4. **R-22** (CI test workflow, ~2 ч) — без него регрессии могут попасть

**Nice-to-have (перед paying, но не blocker):**
5. R-02 (audit gaps, ~6 ч) — для enterprise клиентов
6. R-10 (PII key rotation, ~4 ч) — devOps best practice
7. R-27 (contract update, ~2 ч) — developer-facing
8. R-32 (worker metrics, ~4 ч) — operations
9. R-18 (`_truncated` UI, ~3 ч) — UX

### Post-round (первые 2 недели после VC)
- **R-53** integration test infra (~2–3 ч) — устранить test gap
- **R-05** rate limiter fallback (~1 ч)
- **R-28** rollback script (~3 ч)
- **R-40** `/storage/*` remove (~5 мин)
- **R-45** scope audit_logs DELETE (~1 ч)
- Остальные P2

### Won't fix (не делать без явного запроса)
- P3 accepted risks (18 items)
- P4 not-audited areas (не влезают в scope — honest disclosure уже есть)

---

## Part 6: Как использовать этот файл

- **Для VC demo:** не нужен. Ship QC_AND_RISKS.md §6 + THREAT_MODEL.md (0 HIGH).
- **Для первого платящего:** открыть P1, выбрать must-fix (4 из 9), estimate 1.5 дня.
- **Для tech debt спринта:** P1 + P2 = ~47 ч (~6 рабочих дней) — закрыть всё MEDIUM.
- **Для инвестора, если спросит "что осталось":** P0 = 0, P1 = 9 items documented, P4 = unknowns honestly disclosed.

**Не забыть:**
- Пароль `admin@steloom.com / gorelov` в dev — после demo shipping **сменить** (leaked в чате 2026-10-26)
- `.deploy-meta.json` на demo — authoritative version, `git rev-parse HEAD` в demo ненадёжен (R-38)

---

*End of OPEN_WORK. 51 risks total: 9 CLOSED, 42 open (0 HIGH, 7 MEDIUM, ~5 LOW-MEDIUM, ~18 LOW, 2 ACCEPTED+PLANNED, ~10 accepted by design). See QUALITY_AND_RISKS.md §6 for full risk register and §10 for detailed priorities.*
