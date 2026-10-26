# Steloom / LegalMAS — Reviewer Guide

**Document:** README (Reviewer Guide)
**Version:** 1.4
**Date:** 2026-10-26
**Snapshot (audited baseline):** CONFIRMED — branch `master`, HEAD `f22e3ba1b82348ba1208bd7de8f183ff5331df57` (owner-confirmed 2026-10-26)
**HEAD at completion:** `763f2d9` (7 post-snapshot commits: Q9 fix, R-44 fix, DD package v1.4, deploy hardening R-38/R-39/R-46; all evidence-tracked in `internal/REVIEW_WORKLOG.md`)
**Deployed demo:** git HEAD `97901c8`; content via rsync (R-38)
**Fix log:** Q6 `--proxy-headers` applied 2026-10-26T10:46 UTC (E75); Q9 prompt-injection compact delimiters applied 2026-10-26 to 3 prompt files, smoke-tested (E97); `/storage/*` MinIO bucket verified private (`403`); DB schema verified VARCHAR(50) (E90); Tier 1 pytest 131/131 passed 2026-10-26 (E99, E100); Tier 2 security regression 3/3 passed (E101); end-to-end run completed 17.5 min on synthetic doc (E102); deploy hardening R-38/R-39/R-46 closed 2026-10-26T14:07 UTC (E103) — demo deployed at HEAD 763f2d9
**Review mode:** static + targeted runtime verification + Tier 1 pytest (131) + Tier 2 pytest (3) + end-to-end pipeline run
**Status:** Final for investor delivery — 0 open owner questions
**Methodology:** AI-assisted static analysis + owner-executed verification. Not an independent audit.

## Purpose and scope

This pack supports a pre-seed technical due diligence of Steloom (repository `LegalMAS`): an AI-assisted legal due-diligence SaaS that ingests legal documents, classifies them, runs playbook-driven checks, and surfaces results in a DD Grid.

**What this pack is:**
- A verifiable as-is picture of the code, data model, AI pipeline, security boundaries, and operational posture.
- Evidence-linked claims with explicit limitations.
- All open questions resolved: 5 owner decisions documented, Q6 fix applied and verified at runtime, DB schema drift resolved by direct SQL inspection, test suite executed against HEAD (Tier 1 + Tier 2 = 134/134), end-to-end pipeline run verified on a synthetic document.

**What this pack is not:**
- A security audit, penetration test, or compliance certification (no SOC 2, ISO 27001, GDPR claim).
- A product roadmap.
- An independent human-reviewed audit. This is AI-assisted static analysis and is marked as such.
- A "DD passed" verdict or investment recommendation.

## Snapshot and access

| Field | Value |
|---|---|
| Repository | `https://github.com/701315/LegalMAS` |
| Branch | `master` |
| Commit | `f22e3ba1b82348ba1208bd7de8f183ff5331df57` — CONFIRMED (`git rev-parse HEAD`, 2026-10-26) |
| Working tree (dev) | `M frontend/public/steloom.svg` (1 file; not relevant to DD) |
| Access mode | Owner-provided `git ls-files` + 9 file batches from `/srv/steloom-dev` |
| Deployed demo | `/srv/steloom-demo` — git HEAD `97901c8`; content via rsync (R-38) |
| HANDOVER reference | HANDOVER v7.8 (2026-10-01) referenced `d692e18`; diff `d692e18..f22e3ba` = 182 files, +159,922 / −53,613 lines, 79 non-merge commits (R-37 closed with concrete numbers) |

## Current vs planned

**Current (observed in code at `f22e3ba`, verified end-to-end at E102):**
- Multilingual legal-document pipeline: import → layout/PDF extraction (Docling, 15-layer, 3 quality gates) → PII sanitization → structure (clause tree + LLM clause detection) → chunking (Phase 10 planner, boundary-aware) → classification (L1–L4 cascade) → playbook checks → DD Grid.
- Segmentation (`_segmenter/`, 11 files): boundary detection with 11 weighted signals; swarm protection; TOC/catalog suppression with 6 topological heuristics; purity recovery; V2-aware dormant path; `MAX_REASONABLE_SEGMENTS=15` enforced in public facade.
- Classification cascade: L1 filename (generic-under-specific cap), L2 header (log-normalized scoring, hard/soft exclusions), L3 semantic (multi-window encoding, positive/negative prototypes, adaptive noise suppression).
- LLM clause detection inside structure pipeline: hybrid merge (LLM + numeric fallback), appendices boundary trimming, global routing, list-intro invariant, frozen-safe.
- Multi-tenant data model; project roles (`viewer`, `editor`, `admin`); system roles (`superadmin`, `tenant_admin`, `member`).
- Async orchestration on Celery with `DocumentStageExecution` ledger + outbox pattern + stale-execution/run reapers + DLQ.
- AI inference via Ollama by default (OpenAI, llama.cpp alternatives). **Observed at E102**: 37 LLM calls for a 21-check single-document run, 17.5 min wall-clock on CPU-only Ollama with `qwen2.5:14b`.
- DD Grid V1 with `cell_state` (`defined`/`not_defined`/`not_executed`/`error`), per-cell risk badges, drawer with anchor / location / review status / QC.
- Exports (Excel, Word, JSON); `EXPORT_STARTED`/`EXPORT_COMPLETED`/`EXPORT_FAILED` audited.
- Admin observability: `/tenant/dashboard`, `/tenant/metrics`, `/tenant/logs` audited via middleware; `/tenant/alerts` not audited (read-only).
- Systemd deployment; `deploy-demo.sh` uses `rsync --delete` without git commit in demo (R-38).
- Backups at `/mnt/backups/steloom-demo/releases/` — 15 GB, no rotation (R-39).
- Q6 fix applied 2026-10-26: `--proxy-headers --forwarded-allow-ips=127.0.0.1` in uvicorn; login rate limit now per-client (E75).

**Planned per HANDOVER / owner:**
- B3.6 layout element IDs end-to-end (viewer highlight).
- v3 calibration for remaining doc-type YAML files (most of the 79 non-merge commits between `d692e18` and `f22e3ba` are calibration work).
- Pre-commit / CI hardening.
- Word add-in (owner-stated).
- Legislative monitoring (owner-stated).
- External counterparty/asset integrations (owner-stated).

## How to read this pack

1. **TECHNICAL_OVERVIEW.md** — architecture, module map, product flow, AI pipeline, data model, critical API, deployment.
2. **QUALITY_AND_RISKS.md** — verification, test inventory, security matrix, reliability, AI quality, risk register (R-01…R-45), contradictions (S-01…S-11), owner decisions, priorities.
3. **This file** — orientation, verification matrix, quick start, known limitations.

**`internal/REVIEW_WORKLOG.md`** — trace of what was viewed and closed (not for investor delivery).

## Verification matrix

| Approach | What reviewer gets | Limitations |
|---|---|---|
| Repository review (this pack) | Static as-is view at HEAD `f22e3ba` | No independent human audit |
| **Tier 1 pytest (executed 2026-10-26, E99/E100)** | 131/131 passed — RBAC (11), result semantics (118), presentation smoke (2) | Mocked LLM/DB for most; real DB for smoke presentation |
| **Tier 2 security pytest (executed 2026-10-26, E101)** | 3/3 passed — cross-tenant leakage, unauthorized access, audit identity spoofing | Requires dev DB; wipes `audit_logs` (R-45) |
| **End-to-end pipeline run (executed 2026-10-26, E102)** | Synthetic contract (18 pp., `contract_1.6_real_estate`) → DD Grid; 21 checks; 17.5 min wall-clock | Single synthetic document; CPU-only Ollama; `qwen2.5:14b` base model (not qwen25-legal tuned) |
| Guided code walkthrough | Owner walks through "document → DD Grid" | Depends on owner availability |
| Isolated local run | Reproducible environment | Requires Ollama, DB seed, `.env` |
| Demo login | Live UI demonstration | Demo git HEAD `97901c8`; content via rsync |

## Safe quick start (derived from configuration, NOT executed in this review)
docker compose up -d postgres redis minio office-converter
make install-runtime
make up
make worker
make worker-system
make beat
make worker-heavy-checks
make worker-heavy-enrichment
make worker-heavy-segment-classification
ollama serve
ollama create qwen25-legal -f <Modelfile>
make ollama-warm

Commands derived from `Makefile` / `docker-compose.yml` / `deploy/`.

## Environment requirements

**Confirmed:** Python ≥ 3.11; PostgreSQL 16, Redis 7, MinIO; LibreOffice; Tesseract with eng/rus/deu/fra/tur/ara; Ollama HTTP API; CPU-only default (`torch==2.5.1+cpu`); GPU via `ACCELERATOR=gpu`.

**Not confirmed:** production `.env` values; exact demo-deployed SHA (rsync). At E102, dev used `qwen2.5:14b` (base model), not `qwen25-legal` — parity caveat for demo accuracy.

**Environment variables (names only):** see `core/config.py:Settings` and `.env.example`. Names include: `DATABASE_URL`, `REDIS_URL`, `MINIO_*`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `PII_ENCRYPTION_KEY`, `LLM_PROVIDER`, `LLM_OLLAMA_*`, `LLM_CONTEXT_LIMIT`, `OTEL_ENABLED`, plus ~120 thresholds.

## Acceptance scenario

1. Create deal with `primary_language`.
2. Upload PDF through `POST /deals/{id}/documents/upload`.
3. Wait for pipeline.
4. Start run `POST /deals/{id}/run`.
5. Open `GET /deals/{id}/runs/{run}/dd-grid-v1`.
6. Verify: `cell_values` populated; at least one `defined` cell with `location_page` + `location_clause_ref`; drawer has `display_text` / `review_status` / `execution_status`; QC approve/reject works via `POST /api/v1/qc/review`.

Synthetic fixture acceptable only if clearly marked.

**Verified 2026-10-26 (E102):** acceptance scenario executed against dev at `f22e3ba` on synthetic `Sample_Contract.DOCX` (18 pp.). Run `b7025e4e-...` → `completed` in **17.5 min**; 21 checks scheduled, 21 completed, 0 errors; 21/21 check_results have `structured_data` and `primary_anchor_id`; 42 validated anchors (34 exact_span + 8 fuzzy_span). Full lifecycle in `audit_logs` (16 actions from IMPORT → ANALYSIS_COMPLETED). See `QUALITY_AND_RISKS.md` §1 for details.

## Tests

**Executed during this review (Tier 1 + Tier 2, 2026-10-26, E99/E100/E101):**

| Suite | Passed | Mode |
|---|---|---|
| `tests/api/test_exports_access.py` | 11/11 | mocked RBAC |
| `tests/unit/engine/checks/test_result_semantics*.py` | 118/118 | pure unit |
| `tests/e2e/test_result_presentation_smoke.py` | 2/2 | mocked LLM (after R-44 fix) |
| `tests/security/test_leakage_repro.py` | 3/3 | DB |
| **Tier 1 + Tier 2 total** | **134/134** | **EXECUTED** |

**End-to-end pipeline run (executed 2026-10-26, E102):**

| Aspect | Result |
|---|---|
| Document | `Sample_Contract.DOCX`, 18 pages, `contract_1.6_real_estate`, confidence 0.95 |
| Duration | 17.5 min (16 min pipeline, 1.5 min overhead) |
| Checks | 21 scheduled / 21 completed / 0 errors |
| Results | 14 pass / 0 fail / 1 unclear / 6 no-verdict |
| Anchors | 42 validated (34 exact_span + 8 fuzzy_span), 19 clause_only |
| DD Grid | 21/21 checks with `structured_data` + `primary_anchor_id` |

**Owner-reported baselines (not re-run in this review):**

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `tests/unit/` | 1701 | 37 | — |
| `tests/services/structure/` | 845 | 0 | 10 |
| `tests/services/document_layout/` | 10 | 0 | — |
| `tests/services/` | 1027 | 2 | 10 |
| `tests/unit/engine/` (per v7.2) | 733 | 24 | — |

**CI:** `.github/workflows/` contains only `dependency-audit.yml` — tests **not run in CI** (R-22).

**Caveat (R-45):** `tests/security/test_leakage_repro.py` fixture performs unconditional `DELETE FROM audit_logs` on the shared `mas_dd` DB. Run only against dev DB with backup; never against staging. See `QUALITY_AND_RISKS.md` §6 R-45.

## Known limitations — demo

1. **Ollama model parity** — dev uses `qwen2.5:14b` base model (observed at E102), not the documented `qwen25-legal` (Makefile) or `llama3.1` (config default). Model change can flip extraction quality.
2. **`PII_ENCRYPTION_KEY`** empty in dev → plaintext PII mapping in MinIO (R-07). Acceptable for demo with synthetic documents; not acceptable with real client data.
3. **Legacy runs without instruction snapshot** → non-reproducible.
4. **Demo git HEAD `97901c8`** — `git rev-parse HEAD` in `/srv/steloom-demo` is not a valid indicator of deployed content (rsync). **Authoritative version: `cat /srv/steloom-demo/.deploy-meta.json`** (auto-generated on every deploy: `dev_head`, `deployed_at`, `backup_dir`). **Current: dev_head=`763f2d9`, deployed_at=`2026-10-26T14:07:58+00:00`.** R-38 CLOSED (E103).
5. **`/storage/*` MinIO endpoint** open via Caddy. Bucket verified private (`403` on `/storage/mas-artifacts/`). Recommended: remove `handle /storage/*` from Caddyfile (defense-in-depth; R-40, LOW).
6. **`/ws/*` dead block** in Caddyfile (no matching FastAPI endpoint, `404 application/json`). Not a risk; hygiene cleanup optional (R-41, INFO).
7. **Tier 2 security test wipes audit_logs** on `mas_dd` (R-45, LOW). Manual backup before running if forensic trail is needed.
8. **Backup retention:** `deploy/deploy-demo.sh` rotates backups (>30 days, keep latest 10). Current: 12 dirs, 4.4 GB (was 42 dirs, 15 GB before R-39 fix).

## Known limitations — general

- **No JWT revocation** — deactivation/demotion/password-change only effective on token expiry (8h). ACCEPTED + PLANNED (R-01).
- **`create_planned` unique** — partial indexes exist; `IntegrityError` not caught (R-08, LOW).
- **`_truncated`** (partial JSON salvage) written by backend, not read by frontend (R-18, MEDIUM).
- **Prompt injection** — compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line applied 2026-10-26 to 3 prompt files (`generic_presence.txt`, `classify_document.txt`, `clause_detection.txt`). Smoke-tested via `PromptLoader` (E97). Residual LOW: delimiter escape not sanitized; full closure via `_render_prompt` sanitization deferred (~2h). R-17 FIXED.
- **Audit coverage** — 40+ write actions covered; login/upload-identity/download/admin-user-management not audited. PARTIALLY ACCEPTED + PLANNED (R-02).
- **LLM call count** — observed 37 calls for 21-check doc (E102); aggregate cost not exposed per-run in UI (R-33).
- **Backups** — 15 GB, no rotation (R-39).
- **V2 `anchor_uid` boundary path** — dormant (no producer found in `document_layout/`, `structure/` except consumer, `engine/content/`); if activated, needs confidence validation (R-43, LOW/dormant).
- **Test isolation** — Tier 2 fixture wipes `audit_logs` unconditionally (R-45, LOW). Scope DELETE by tenant_id or require separate test DB.
- **R-44 CLOSED** — `test_result_presentation_smoke.py` fixture drift fixed 2026-10-26 (E100); no runtime impact.

## Contact

Owner-provided contact details were not supplied. Do not assume roles, names, or contact info from this pack.

---

*End of README. Audited baseline `f22e3ba`; HEAD at completion `763f2d9` (7 post-snapshot commits). Demo deployed at `763f2d9` 2026-10-26T14:07 UTC via `.deploy-meta.json` (E103). Q6 fix verified both pre- and post-deploy (5×401 + 2×429). DB schema verified VARCHAR(50). Tier 1+2 pytest 134/134 passed (E99–E101). End-to-end run 17.5 min (E102). 0 open owner questions. 45 risks in final status: R-38/R-39/R-44/R-46 CLOSED, R-45 OPEN LOW.*
