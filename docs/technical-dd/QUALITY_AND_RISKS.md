# Steloom / LegalMAS — Verification, Security and Limitations

**Document:** QUALITY_AND_RISKS
**Version:** 1.5
**Date:** 2026-10-26
**Snapshot:** CONFIRMED — branch `master`, HEAD `f22e3ba1b82348ba1208bd7de8f183ff5331df57` (2026-10-26); working tree `M frontend/public/steloom.svg` (not read). HANDOVER v7.8 referenced `d692e18`; diff = 182 files, +159,922 / −53,613, 79 non-merge commits.
**Deployed demo:** git HEAD `97901c8` (rsync; R-38)
**Fix log:** Q6 fix applied 2026-10-26T10:46 UTC (E75); `/storage/*` MinIO bucket verified private (`403`); DB `result`/`severity` verified `VARCHAR(50)` (E90); Q9 prompt-injection compact delimiters applied 2026-10-26, smoke-tested (E97); Tier 1 pytest executed 2026-10-26 (E99): 131/131 passed; R-44 test fixture drift closed (E100); Tier 2 security pytest 3/3 passed (E101); end-to-end pipeline run completed 17.5 min on synthetic doc (E102); deploy hardening R-38/R-39/R-46 closed 2026-10-26T14:07 UTC (E103) — demo deployed at HEAD 763f2d9; threat model v1.0 + R-07 CLOSED + R-24/R-03/R-33 severity upgrade + R-49/R-50/R-51 new (E104); dev end-to-end run 15.2 min on synthetic doc + race 409 verified end-to-end (E105, E106); R-33/R-49/R-52/R-03 CLOSED, R-53 NEW LOW test gap; demo re-deployed at e1325f9 2026-10-26T17:13 UTC (E106), V1–V10 post-deploy verified
**Review mode:** static + targeted Q6 runtime verification + DB schema check + Tier 1 pytest + Tier 2 pytest + end-to-end pipeline run
**Status:** Final for investor delivery — 0 open owner questions
**Methodology:** AI-assisted static analysis + owner-executed verification. Not an independent audit.

## 1. What was verified and how

**Verified statically (batch A–J):**
- Actual HEAD `f22e3ba...`; working tree `M frontend/public/steloom.svg`; diff `d692e18..f22e3ba` = 182 files, +159,922 / −53,613 lines, 79 non-merge commits.
- Authentication: JWT-only; `is_active` filtered at login.
- JWT lifecycle: no revocation (grep confirms no `revoke`, `blacklist`, `refresh_token`, `password_changed_at`, `token_version`, `jti`).
- Authorization: three-tier (`get_scoped_*`, `require_project_role`, `require_tenant_scope_access`).
- PII reveal: `editor`+ (`pii_reveal.py:85`); no `can_reveal_pii`; pre-audit mandatory; no rate limit (R-03, R-04).
- Export access: `_get_scoped_export_or_404` + `require_project_role(viewer, editor, admin)`. Lifecycle audited; download not (R-13).
- Audit coverage: middleware covers 6 suffix paths; endpoint-level covers ~40 write actions; login, upload endpoint, download export, admin user management, `/alerts`, read-only lists not audited (R-02).
- Rate limiter: `RedisStorage` + `FixedWindowRateLimiter`; `hit()` not wrapped (R-05); Q6 fix applied (`--proxy-headers`; E75).
- File validation: extension, size, magic bytes; HEIC/HEIF/WebP/BMP not checked (R-24).
- Prompt injection: **FIXED 2026-10-26** — compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line in 3 prompt files (`generic_presence.txt`, `classify_document.txt`, `clause_detection.txt`); smoke-tested via `PromptLoader` (E97). Residual LOW: delimiter escape not sanitized. R-17 CLOSED → residual LOW.
- Layout pipeline: 15 layers; 3 quality gates; `QualityGateError` → QUARANTINE + `processing_error_details`; no `LAYOUT_QUARANTINED` audit event (R-31).
- Structure pipeline: per-segment; TOC analysis + guard; `LLMClauseDetector.refine_tree()`; hierarchy; cross-refs; quality gate.
- Segmentation (11 files): 11 weighted signals; swarm protection; `detect_body_internal_boundary_listing`; TOC/catalog suppression with 6 topological heuristics; purity recovery (≤3 iterations); V2-aware path (`anchor_uid` changes, confidence=0.95 — dormant, R-43); `MAX_REASONABLE_SEGMENTS=15` enforced in `segmenter.py` (R-42 CLOSED); `SEGMENT_CONFIDENCE_THRESHOLD` from settings.
- Classification cascade L1–L3: L1 filename with generic-under-specific cap; L2 header with log-normalized scoring (max_expected=5.0), hard/soft exclusions; L3 semantic with multi-window encoding (head 800/middle 600/tail 400; weights 0.50/0.30/0.20), positive/negative prototypes (BGE-M3), adaptive noise suppression (margin<0.05 AND pos_sim<0.65 → excluded from voting).
- Clause detection: hybrid LLM + numeric-only fallback, appendices boundary trimming, global routing, list-intro invariant, frozen-safe, LLM usage recorded.
- Chunk planner: 3 modes; boundary-aware splitting; mode C not alerted (R-34).
- Instruction snapshot: strict mode forbids filesystem fallback.
- `_truncated` written by backend, not read by frontend (R-18).
- `result`/`severity` — model `String(50)`; DB `information_schema` confirms `VARCHAR(50)` (E90); `_safe_truncate(20)` is no-op for current values (R-09 CLOSED).
- `create_planned` race: unique partial indexes exist (`bc56177ec084`); `IntegrityError` not caught (R-08, LOW).
- Backups: retention via `rotate_backups()` (30d + keep 10); after deploy 2026-10-26: 12 dirs, 4.4 GB (was 42 dirs, 15 GB). R-39 CLOSED (E103).
- Rollback script: none (R-28).
- Worker `/metrics`: not implemented; LLM alerts sleeping (R-32).
- `chunk_planner` mode C: no alert (R-34).
- `AUDIT_FINAL_2026-10-17.txt`: playbook-YAML only (R-36, S-09).
- Caddyfile: `/api/*` with XFF; `/storage/*` proxy to MinIO; `/ws/*` dead block; root → frontend dist.
- `anchor_uid` producer: not found in `document_layout/`, `structure/` (except consumer `_segmenter/candidates.py`), `engine/content/` via grep → V2 boundary path dormant (R-43 LOW).
- Runtime LLM config (E98): `LLM_CONTEXT_LIMIT=12288` in demo `.env` (code default 32768); L4 worst-case `skeleton_tokens=3778` + `chatml_overhead=242` + `fragment_budget=7756`; overhead_ratio 32.8%.
- Test fixture drift (R-44): `test_result_presentation_smoke.py` was stale after `ResultPresentationTranslation` contract added 3 required args and `CheckResult.structured_data` expansion. **FIXED 2026-10-26 (E100)** — see §2.

**Verified at runtime:**

**Q6 fix (E75):**
- `systemd` has `--proxy-headers --forwarded-allow-ips=127.0.0.1`.
- 7 login attempts via `--resolve` → `5×401 + 2×429`.
- `journalctl` shows `Rate limit exceeded` with `identity="127.0.0.1"` and `request_id`.

**Other runtime checks:**
- `/storage/mas-artifacts/` → `HTTP/2 403` (`server: MinIO`); bucket private (E74).
- `/ws/` → `HTTP/2 404 application/json` (E76).
- DB `result` and `severity` → `character varying(50)` via `information_schema.columns` (E90).

**Tier 1 pytest (E99, E100) — executed 2026-10-26 at HEAD `f22e3ba`:**

| Suite | Passed | Mode |
|---|---|---|
| `tests/api/test_exports_access.py` | 11/11 | mocked RBAC |
| `tests/unit/engine/checks/test_result_semantics*.py` | 118/118 | pure unit |
| `tests/e2e/test_result_presentation_smoke.py` | 2/2 (after fix) | mocked LLM |
| **Tier 1 total** | **131/131** | — |

Initial run of `test_result_presentation_smoke.py` → 2 failed (pre-existing test/spec drift, R-44). Fixtures updated (E100): `make_translation_ru` got `localized_structured_data`/`dd_request_text`/`dd_request_addressee`; `make_check_result` got `structured_data=None`; assertion rewritten to summary-based behavior (batch swallows `TransientError`); unused `TransientError` import removed; `ruff check --fix` cleaned trailing whitespace. Final: 2/2 passed, `ruff check` clean.

**Tier 2 security pytest (E101) — executed 2026-10-26 against dev `mas_dd`:**

| Test | Result |
|---|---|
| `test_reproduce_unauthorized_deal_access` | PASSED (401) |
| `test_reproduce_cross_tenant_evidence_leakage` | PASSED (404) |
| `test_reproduce_audit_identity_spoofing` | PASSED (actor != X-User-Id) |
| **Tier 2 total** | **3/3** |

Security regression guard verified at runtime (cross-tenant isolation, unauthorized access, audit identity spoofing). Caveat: fixture performs unconditional `DELETE FROM audit_logs` on shared `mas_dd` — 9283 pre-existing records wiped; manual backup available (`/tmp/audit_logs_backup_20261026-121932.sql`, 5.3 MB, 9317 lines). New finding → R-45 (LOW, OPEN).

**End-to-end pipeline run (E102) — executed 2026-10-26 on synthetic doc:**

- `run_id`: `b7025e4e-7824-4ba3-a200-3817696012e7`
- `deal_id`: `ad27bbf4-c1d1-4340-bbbb-27880860d762`
- Status: `completed`; `has_errors=f`
- Duration: **17.5 min** (started 12:29:35 UTC, completed 12:47:05 UTC)
- `pipeline_strategy=REUSE_STRUCTURE`, `checks_mode=global_and_doc_type`, `checks_scope=null`, `analysis_language=null`

Document:
- `Sample_Contract.DOCX`, 18 pages, `doc_type=contract_1.6_real_estate`, `classification_confidence=0.95`, `status=enriched`

Check results (21 planned / 21 executed):
- `execution_status=SUCCESS`: 21
- `result=pass`: 14; `result=fail`: 0; `result=unclear`: 1; other/no-verdict: 6; `null_result`: 0

Anchors:
- `exact_span`: 34 (34 validated)
- `fuzzy_span`: 8 (8 validated)
- `clause_only`: 19 (0 span to validate — expected)
- Total validated spans: **42/42**

LLM usage (37 calls, model `qwen2.5:14b` on Ollama):

| Stage | Calls | Prompt tok | Completion tok | Avg ms |
|---|---|---|---|---|
| `checks_extraction_llm` | 20 | 130,022 | 11,671 | 21,851 |
| `result_presentation_translation` | 12 | 8,036 | 3,153 | 7,245 |
| `run_summary_pass_b` | 1 | 3,191 | 823 | — |
| `structure_clause_detection` | 1 | 2,548 | 374 | — |
| `structure_semantic_enrichment` | 1 | 2,827 | 161 | 6,814 |
| `run_summary_pass_a` | 1 | 2,069 | 1,415 | — |
| `classification_l4` | 1 | — | — | — |
| **Total** | **37** | **~148k** | **~17.6k** | — |

Audit trail (16 distinct action types, 27 rows total, `deal_id` scoped):
- IMPORT, LANGUAGE_DISCOVERY_STARTED, LANGUAGE_DISCOVERY_COMPLETED, SET_DEAL_PRIMARY_LANGUAGE, SET_DEAL_PLAYBOOK, ANALYSIS_STARTED, PRIMARY_SOURCE_READY, SANITIZE, CHUNK_BUILD_COMPLETED, CLASSIFY_COMPLETED, STRUCTURE_COMPLETED, LEGAL_UNITS_ENRICHMENT_COMPLETED, ANALYSIS_COMPLETED, result_presentation.requested, result_presentation.claimed, result_presentation.translated (×12)

DD Grid shape:
- unique_checks: 21
- total_results: 21
- with_structured_data: 21/21
- with_anchor: 21/21

**Verification scope note:** end-to-end run used `qwen2.5:14b` (base model), not `qwen25-legal` documented in Makefile or `llama3.1` config default. Model parity caveat applies to demo accuracy (see §4 known gaps, R-33). Single synthetic document; not a benchmark of accuracy. Wall-clock on GPU (RTX 5060 Ti, 49/49 layers offloaded) — dominated by non-LLM stages (Docling layout, OCR, segmentation, office-converter), not LLM inference.

**Owner-reported:** test baselines for `tests/unit/`, `tests/services/`, `tests/unit/engine/` (see §2); anti-hypotheses B7.3/B7.7/B7.8 rejected; HEAD `f22e3ba`.

**Not verified / UNKNOWN:** demo content correspondence to `f22e3ba` (rsync); deep `_element_classifier/`, `_heading_builder/`, `_heading_scoring/`, `_hierarchy_builder/`, `_models/` (except `_identity.py`), `semantic_enrichment/`, `coherence/`, `cohesion/`, `chunk_planner/_types.py`, `_clause_detector/routing.py` (~70 files); full alembic history; legal/contract ownership; performance/cost benchmarks; `AUDIT_FINAL` intent; `anchor_uid` producer (R-43).

## 2. Test inventory

**Executed during this review (Tier 1 + Tier 2, 2026-10-26):**

| Suite | Passed | Failed | Mode |
|---|---|---|---|
| `tests/api/test_exports_access.py` | 11 | 0 | mocked RBAC |
| `tests/unit/engine/checks/test_result_semantics*.py` | 118 | 0 | pure unit |
| `tests/e2e/test_result_presentation_smoke.py` | 2 | 0 | mocked LLM (after R-44 fix) |
| `tests/security/test_leakage_repro.py` | 3 | 0 | DB |
| **Total** | **134** | **0** | **EXECUTED** |

Additional end-to-end pipeline run (E102): 1 synthetic document → DD Grid in 17.5 min, 21/21 checks completed, 42 validated anchors.

**Owner-reported baselines (not re-run in this review):**

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `tests/unit/` | 1701 | 37 | — |
| `tests/services/structure/` | 845 | 0 | 10 |
| `tests/services/document_layout/` | 10 | 0 | — |
| `tests/services/` | 1027 | 2 | 10 |
| `tests/unit/engine/` (per v7.2) | 733 | 24 | — |

**Selected test files reviewed statically:** `test_leakage_repro.py` (3 regressions); `test_exports_access.py` (9 RBAC mocked); `test_result_presentation_smoke.py` (mocked LLM).

**CI:** `.github/workflows/dependency-audit.yml` only — tests **not run in CI** (R-22).

**Coverage:** no `pytest-cov` report found.

**Caveat (R-45):** `tests/security/test_leakage_repro.py` fixture performs unconditional `DELETE FROM audit_logs` on shared `mas_dd` DB. Manual backup before run; not for staging. See §6 R-45.

**Tier 1 pre-fix failures (E99 → E100):** initial `test_result_presentation_smoke.py` run 2 failed → pre-existing test/spec drift (R-44). No runtime regression from Q6 or Q9 fix. Fixtures updated; final 2/2 passed.

## 3. Security and privacy

| Control | Impl. | Evidence | Limitation | Status |
|---|---|---|---|---|
| Authentication | JWT, bcrypt | `auth.py`, `auth_service.py` | No revocation, no refresh, 8h TTL | R-01 ACCEPTED + PLANNED |
| Tenant isolation | `get_scoped_*` + `require_project_role` | `security.py`; **Tier 2 test passed** (cross-tenant → 404, unauthorized → 401) | `tenant_admin` bypasses project role | Owner-intent accepted; security regression guard verified (E101) |
| Logout | Not server-side | — | Client-side only | Owner-intent accepted |
| Rate limiting (login) | `limits` + Redis; 5/min | `rate_limit.py`; `--proxy-headers` (Q6 fix) | No fallback if Redis down (R-05) | R-06 CLOSED; R-05 MEDIUM |
| Password reset | Not found | — | — | Owner-intent accepted |
| PII encryption | Fernet when key set | `pii_encryption.py` | Dev-mode plaintext (R-07); no rotation (R-10) | R-07 LOW-MEDIUM; R-10 MEDIUM |
| PII reveal | `editor`+; pre-audit; no rate limit | `pii_reveal.py:85` | Editor can trigger; no separate flag | R-03 MEDIUM-HIGH; R-04 ACCEPTED + PLANNED |
| File upload validation | Extension, size, magic | `file_validator.py` | HEIC/HEIF/WebP/BMP not checked (R-24) | R-24 LOW |
| Prompt injection defense | Compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line in 3 files (2026-10-26, E97); smoke-tested via `PromptLoader` | `prompts/*` | Delimiter escape not sanitized; targeted attack only | R-17 FIXED (residual LOW) |
| LLM grounding | Token-overlap | `llm_detector.py` | Does not block malicious found=True | Mitigation, not defense |
| Audit coverage | Middleware + endpoint | `audit.py`, endpoints; **observed 16 lifecycle actions at E102** | Login, upload-id, download, admin-users, `/alerts`, read-only — unaudited | R-02 PARTIALLY ACCEPTED + PLANNED |
| Audit identity spoofing | `X-User-Id` ignored; real `actor` from JWT | Tier 2 test passed (E101) | — | Verified |
| CI security | `pip-audit` | workflow | No tests/bandit/ruff | R-22 MEDIUM |
| Secrets in repo | None found; dev values in compose | `docker-compose.yml` | MinIO root password literal | R-29 LOW |
| CORS | Allowlist; validator forbids `*` | `config.py`, `main.py` | — | — |
| GDPR / compliance | No claims | `pii_*.py` | No DPA / retention visible | Owner-intent accepted |
| PDF export `inline` | `_build_content_disposition` | `exports.py` | Potential XSS via malicious PDF | R-13 LOW-MEDIUM |
| `/storage/*` MinIO proxy | Caddy `strip_prefix` → MinIO | `/etc/caddy/Caddyfile` | Bucket private (`403`); endpoint exposed | R-40 LOW |
| `/ws/*` proxy (dead block) | Caddy `reverse_proxy` | `/etc/caddy/Caddyfile`; no matching endpoint | Not a risk; hygiene cleanup | R-41 INFO |
| Test isolation (QA) | `test_leakage_repro.py` fixture | R-45 (E101) | Wipes `audit_logs` unconditionally | R-45 LOW (OPEN) |

## 4. Reliability and operations

**Implemented:** durable stage ledger; outbox; retry with backoff; stale reapers; DLQ; finalize guards; 3 layout quality gates; chunk planner; export lifecycle audit; 13 alert rules; unique partial indexes on plan items; `--proxy-headers` (Q6 fix); segmentation `MAX_REASONABLE_SEGMENTS=15` enforcement.

**Observed at E102 (2026-10-26):** pipeline completed in 17.5 min on GPU (RTX 5060 Ti, 49/49 layers offloaded; wall-clock dominated by non-LLM stages) for 18-page synthetic contract (21 checks); full lifecycle in `audit_logs`; 21/21 check_results with `structured_data` + `primary_anchor_id`; no stale executions. Demonstrates reliability of orchestration for a small synthetic doc; not a benchmark.

**Known gaps:** `IntegrityError` on `create_planned` not caught (R-08); retry overwrites `CheckResult`; `_shared_llm_client` module-level; backup rotation missing (R-39); no rollback script (R-28); LLM alerts sleeping (R-32); mode C not alerted (R-34); `QualityGateError` path missing `LAYOUT_QUARANTINED` audit (R-31); demo git drift (R-38); test fixture wipes `audit_logs` (R-45).

**Not measured:** latency (measured for one run at E102), throughput, cost per document (aggregate; per-check events recorded), LLM accuracy, long-run behaviour, memory footprint.

## 5. AI quality — limitations

- No formal accuracy benchmarks. `GATE_*` thresholds not connected to runtime gate.
- Confidence = LLM-self-reported × grounding heuristic; not calibrated probability.
- Grounding suppresses weak evidence; does not eliminate hallucinations.
- Prompt injection defenses in 3 files (R-17 FIXED, residual LOW). Clause detection bounded by numeric-only fallback.
- `_truncated` not surfaced in UI (R-18).
- LLM call count observed at E102: **37 calls for 21-check doc** (extraction 20, translation 12, summaries 2, clause detection 1, enrichment 1, L4 1). Aggregate cost not exposed in UI (R-33).
- Model parity caveat: E102 ran with `qwen2.5:14b` (base model), not `qwen25-legal` documented in Makefile. Model change can flip extraction quality.
- `ROLE_MAP` PII tokenizer only RU/EN (R-11).
- L3 adaptive noise suppression reduces false voting signals but doesn't eliminate them.
- Single synthetic document verification at E102; not representative of all doc types.

## 6. Risk register

Severity uses qualitative reasoning (impact × reachability). **No CVSS assigned.**

| ID | Area | Finding | Type | Evidence | Impact | Severity | Mitigation | Status |
|---|---|---|---|---|---|---|---|---|
| R-01 | Auth | JWT not invalidated on deactivation/demotion/password change | STATIC (grep) | `auth.py`, `auth_service.py` | Access until token expiry (8h) | **MEDIUM** | — | **ACCEPTED + PLANNED** (owner 2026-10-26; plan: ~8h to enterprise) |
| R-02 | Audit | Login, upload-id, download, admin-users, `/alerts`, read-only not audited | STATIC (grep) | `audit.py`, endpoints | Gaps in incident response / compliance trail | **MEDIUM** | 40+ write actions audited (16 lifecycle actions observed at E102) | **PARTIALLY ACCEPTED + PLANNED** (owner; ~6h to first paying) |
| R-03 | PII | No rate limit on PII reveal | STATIC + EXECUTED | `pii_reveal.py:85,119`; `rate_limit.py`; E104, E106 | Exfiltration amplifier: compromised editor → bulk PII reveal | **CLOSED** | `check_pii_reveal_rate_limit` 10/min per user (commit `56bb76d`); scope=`pii_reveal`, identity=`user.id` (not IP — Caddy). 8/8 tests passed (2 new rate-limit tests). | **CLOSED** (E106) — 2026-10-26 |
| R-04 | PII | `editor` = full PII reveal; no `can_reveal_pii` | STATIC (grep) | `pii_reveal.py:85` | Junior user sees PII | **MEDIUM** | Pre-audit mandatory | **ACCEPTED + PLANNED** (owner; plan: flag + confirm dialog ~4h) |
| R-05 | Availability | Rate limiter no fallback if Redis down | STATIC (not executed) | `rate_limit.py` | Login 500 instead of 429 | **MEDIUM** | — | OPEN (fix: try/except ~1h) |
| R-06 | Rate limit | Login keyed by IP; no `--proxy-headers` | STATIC → EXECUTED | systemd + Caddyfile + `journalctl` | All users share bucket (was) | **CLOSED** | Fix applied 2026-10-26T10:46; E75 | **CLOSED** |
| R-07 | PII | Dev-mode plaintext PII if key empty | STATIC → EXECUTED | `pii_encryption.py:97-100`; `.env` verified (E104) | Plaintext mapping in MinIO in dev (was assumed) | **CLOSED** | `PII_ENCRYPTION_KEY` verified set in both dev (43 chars) and demo (43 chars Fernet base64); `pii_encryption.py:97` rejects invalid format | **CLOSED** (E104) — 2026-10-26 |
| R-08 | Orchestration | Concurrent `create_planned` — `IntegrityError` not caught | STATIC | migration `bc56177ec084`, call sites | Task failure (not duplicate) | **LOW** | Partial unique indexes | OPEN (fix: catch ~30m) |
| R-09 | Data | DB schema verified: `result`/`severity` are `VARCHAR(50)`; `_safe_truncate(20)` is no-op for current values | STATIC + EXECUTED | SQL `information_schema.columns` | Hot-fix masks nothing; can be removed in cleanup | **LOW** | Schema already correct | **CLOSED** (optionally remove dead-code) |
| R-10 | PII | No key rotation | STATIC (grep) | `pii_encryption.py` | Old mappings unreadable after key change | **MEDIUM** | — | OPEN (plan ~4h) |
| R-11 | PII | ROLE_MAP only RU/EN | STATIC | `pii_tokenizer.py` | Role hints missing other languages | **LOW** | Opt-in | Accepted |
| R-12 | PII | Token format `PERSONNAME1` collision | STATIC | `pii_tokenizer.py` | Low probability | **LOW** | — | Accepted |
| R-13 | Exports | PDF `inline`; download not audited | STATIC | `exports.py` | Potential PDF XSS; download untracked | **LOW-MEDIUM** | Lifecycle audited | OPEN (audit on download ~1h) |
| R-14 | Auth | No `password_changed_at` / `last_login_at` | STATIC | `user.py` | No session invalidation on password change | **LOW** | — | OPEN (add columns ~1h) |
| R-15 | Logging | Pre-auth `tenant_id` from `X-Tenant-Id` | STATIC | `audit.py` | Forensic confusion | **INFO** | — | Accepted |
| R-16 | Exports | Docstring "no role check" but code checks | STATIC | `exports.py` | Misleading | **INFO** | — | Open (fix docstring 5m) |
| R-17 | AI | Prompt injection: compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line applied 2026-10-26 to 3 files (E97); token budget verified (E98): `fragment_budget=7756` at `LLM_CONTEXT_LIMIT=12288`; clause detection has conservative numeric-only fallback | STATIC → EXECUTED | `prompts/*`; smoke test `PromptLoader`; E102 run used same prompts | Delimiter escape (`</UNTRUSTED_DOCUMENT_TEXT>` inside document text) not sanitized — targeted attack only; L4 budget safe (32.8% overhead) | **LOW** (was MEDIUM-HIGH) | Delimiters + prompt instruction + fallback + budget check | **FIXED 2026-10-26 (residual LOW)** — optional sanitization in `_render_prompt` for full closure (~2h) |
| R-18 | AI | `_truncated` written, not read by frontend | STATIC (grep) | `extraction_llm_detector.py`, `DDGridV1Drawer.tsx` | Partial value shown as complete | **MEDIUM** | — | OPEN (fix ~3h) |
| R-19 | AI | Weak grounding (0.1–0.3) may be used for extraction | STATIC | `extraction.py` | Field from weakly grounded text | **LOW-MEDIUM** | Anchor suppressed | Accepted |
| R-20 | Frontend | Backend viewer download, frontend hides | STATIC | `exports.py`, `permissions.service.ts` | Viewer bypasses UI | **LOW** | — | Owner-intent accepted |
| R-21 | Frontend | `not_applicable` label not localized | STATIC | `DDGridV1Drawer.tsx` | UI shows raw string | **LOW** | Tone mapped | Open (i18n key 5m) |
| R-22 | CI | No test/build/lint workflow | STATIC | `.github/workflows/` | Bugs reach master | **MEDIUM** | — | OPEN (plan ~2h) |
| R-23 | Upload | Temp ZIP not cleaned on success | STATIC | `deals/documents.py:222,255-263` | Disk leak | **LOW-MEDIUM** | — | OPEN (fix ~30m) |
| R-24 | File validation | HEIC/HEIF/WebP/HEIF magic not checked; **magic fail → VALID/unknown, not QUARANTINE** (`file_validator.py:200-215`) | STATIC + EXECUTED | `file_validator.py:200-215`; `IMPORT_ALLOWED_EXTENSIONS` includes `.webp,.heic,.heif`; MAGIC_BYTES does NOT (E104) | Malicious content with `.heic`/`.webp` ext → `unknown` passes to pipeline; downstream parser sole defense | **LOW-MEDIUM** (was LOW) | Downstream parser; extension whitelist | **OPEN** — add HEIC/WebP magic detection; change magic fail from VALID/unknown → QUARANTINE |
| R-25 | Semantics | `pass` + `clause_missing` possible | STATIC | `result_semantics.py` | Semantic contradiction | **MEDIUM** | — | Owner-intent accepted |
| R-26 | Docs | `prompts/README.md` empty | STATIC | empty file hash | No prompt docs | **LOW** | — | Open (populate 30m) |
| R-27 | Contract | `dd_grid_v1_contract.md` stale | STATIC | contract vs builder | Reviewer misled | **MEDIUM** | — | OPEN (update 2h) |
| R-28 | Deploy | No rollback script | STATIC | `deploy/` | Manual rollback | **LOW-MEDIUM** | — | OPEN (plan ~3h) |
| R-29 | DevOps | Dev default secrets hardcoded in code + compose: `MINIO_SECRET_KEY="Kesko-701315"` (config.py:57), `DATABASE_URL` with password (config.py:48), `POSTGRES_PASSWORD` + `MINIO_ROOT_PASSWORD` (docker-compose.yml). All overridable via .env; committed to git | STATIC | `config.py:48,57`; `docker-compose.yml` | Dev-only defaults but visible in repo; production relies on .env override | **LOW** | `.env` overrides; production validator blocks empty keys | **OPEN** — move all defaults to `.env.example`, require explicit set in production |
| R-30 | Docs | Only one ADR | STATIC | `docs/adr/` | Rationale not captured | **LOW** | HANDOVER covers some | Open (incremental) |
| R-31 | Layout | `QualityGateError` → QUARANTINE + details; no `LAYOUT_QUARANTINED` audit | STATIC (grep) | `build_primary_language_source.py:319-390` | Lifecycle correct; audit incomplete | **LOW-MEDIUM** | `processing_error_details` structured | OPEN (audit event 30m) |
| R-32 | Monitoring | LLM alerts sleeping — no worker scrape | STATIC + OWNER-REPORTED | `operations.yml`, `src/ops/instrument.py` | LLM crash visible indirectly | **MEDIUM** | — | OPEN (plan: worker `/metrics`) |
| R-33 | AI cost | Observed 37 LLM calls per 21-check doc at E102; **no concurrent run guard** — `try_start_run` only PENDING→RUNNING, no `(deal_id, status=running)` uniqueness; user can start N parallel runs | STATIC + EXECUTED | `run_repo.py:306`; `runs.py:48`; E104, E106 | Cost amplification: 50 calls/run × N parallel runs; no quota | **CLOSED** | (a) partial unique index `uq_runs_one_active_per_deal WHERE status IN ('pending','running')` (migration `bf78307e1293`, commit `cf315e4`); (b) API `IntegrityError` → 409 + `X-Active-Run-Id` header (commit `fa092ed`); (c) `db.rollback()` before logger + cached `deal_tenant_id_str` (MissingGreenlet fix, commit `e1325f9`); (d) curl-verified end-to-end on dev: 2nd POST → 409 with `X-Active-Run-Id` = active run uuid (E106); (e) migration integrity test: 2nd concurrent INSERT → unique_violation | **CLOSED** (E106) — 2026-10-26 |
| R-34 | Observability | Mode C not alerted | STATIC (grep) | `monitoring/alerts/` | Degraded chunking invisible | **LOW-MEDIUM** | — | OPEN (alert 30m) |
| R-35 | Data ordering | Geometric sort fallback for missing bbox | STATIC | `_core_builder.py` | Silent ordering change | **LOW** | — | Accepted |
| R-36 | Docs | `AUDIT_FINAL` scope = playbook only | STATIC (grep) | audit file + scripts | Reader may misinterpret | **LOW** | — | Open (clarify in HANDOVER) |
| R-37 | Docs | HANDOVER references `d692e18`; actual HEAD `f22e3ba`; diff = 182 files, +159,922/−53,613, 79 non-merge commits | EXECUTED | HANDOVER §1; `git diff --stat`, `git log` | HANDOVER significantly stale | **INFO** (was MEDIUM) | — | **CLOSED (INFO)** |
| R-38 | Deploy | `deploy/deploy-demo.sh` rsync without git commit | CONFIRMED → CLOSED | `deploy/deploy-demo.sh`; `/srv/steloom-demo/.deploy-meta.json` (E103) | `git rev-parse HEAD` in demo ≠ deployed content; mitigated by auto-gen deploy-meta | **LOW** | `.deploy-meta.json` auto-generated on every deploy: `{dev_head, deployed_at, deployer, host, backup_dir}`. Current dev_head=`e1325f9`, deployed_at=2026-10-26T17:13:48 | **CLOSED** (E103) — 2026-10-26 |
| R-39 | Ops | Backups growth unbounded (was 42 dirs, 15 GB) | CONFIRMED → CLOSED | `deploy/deploy-demo.sh`; `/mnt/backups/steloom-demo/releases/` (E103) | Disk growth | **LOW** | `rotate_backups()` — 30 days + keep latest 10; after deploy 2026-10-26: 12 dirs, 4.4 GB | **CLOSED** (E103) — 2026-10-26 |
| R-40 | Deploy | `/storage/*` MinIO proxy exposed; bucket private (`403`) | STATIC + EXECUTED | `/etc/caddy/Caddyfile`; `curl /storage/mas-artifacts/` → 403 | Attack surface; not a data leak | **LOW** | Bucket private | **ACCEPTED** (recommend removing block) |
| R-41 | Deploy | `/ws/*` dead block in Caddyfile (no matching endpoint) | STATIC + EXECUTED | `/etc/caddy/Caddyfile`; `curl /ws/` → 404 | Not a risk; hygiene | **INFO** | — | **ACCEPTED** (optional cleanup) |
| R-42 | Segmentation | `MAX_REASONABLE_SEGMENTS=15` enforced in `segmenter.py` public facade → single-segment fallback | STATIC | `segmenter.py:200-213` | Protection exists | **CLOSED** | Fallback confirmed | **CLOSED** |
| R-43 | Segmentation | V2 `anchor_uid` path (`_collect_v2_anchor_boundaries`, confidence=0.95) dormant — no `anchor_uid` producer found in `document_layout/`, `structure/` (except consumer), `engine/content/` | STATIC (grep) + UNKNOWN | `_segmenter/candidates.py`, grep | If V2 pipeline activates and emits `anchor_uid`, any change → boundary with 0.95 confidence | **LOW** (dormant) | `_is_v2_format` requires ≥30% V2 elements | OPEN (LOW, dormant) — verify semantics if V2 pipeline activates |
| R-44 | Tests | Pre-existing test/spec drift: `test_result_presentation_smoke.py` fixtures not updated after `ResultPresentationTranslation` contract (3 new required args) and `CheckResult.structured_data` expansion; `TransientError` exception no longer propagated (batch swallows) | STATIC → EXECUTED | `pytest` (E99) → fixtures updated (E100) → 2/2 passed | Test suite drift signals fixture maintenance lag; not a runtime bug | **LOW** | Fixtures updated 2026-10-26; unused `TransientError` import removed; `ruff check --fix` cleaned whitespace | **CLOSED** (E100) |
| R-49 | API auth | **`model_configs.py` POST/PATCH/DELETE without auth** — `create_model_config`, `update_model_config`, `delete_model_config` (`model_configs.py:65,113,171`) have only `Depends(get_db)`, no `get_current_user`. **Live confirmed:** `GET → 200`, `POST (empty) → 422` (pydantic validates before handler, no auth gate). Schema has no `base_url`/`api_key` → no exfil/RCE | EXECUTED | `model_configs.py:65,113,171`; E104, E106 | Unauth write/delete model configs → DoS via DELETE + pipeline integrity via PATCH embeddings; not data exfil | **CLOSED** | (a) `require_superadmin()` Depends guard in `security.py` (commit `061c7e3`); (b) POST/PATCH/DELETE → `Depends(require_superadmin)`, GET/usage remain `Depends(get_current_user)` for editor workflow; (c) frontend hides write buttons for non-superadmin + read-only banner (commit `524988b`); (d) 15/15 tests (3 guard unit + 12 HTTP: 401/403 for member, 403 for tenant_admin, 422 for superadmin empty body, 200 for member GET) | **CLOSED** (E106) — 2026-10-26 |
| R-50 | API auth | `documents/exports.py:196 _build_download_headers` builds raw `Content-Disposition: attachment; filename="{user_filename}"` without `\r\n` sanitization; `import_bundle_use_case.py:377` does `os.path.basename()` without CRLF strip. Starlette 0.41.3 accepts CRLF in header values | STATIC + EXECUTED | `exports.py:196,267,332,408`; `pdf_urls.py:36-70` uses safe RFC 5987 (comparison) (E104) | HTTP response splitting via `Content-Disposition`; 3 endpoints vulnerable. `pdf_urls.py` safe — extract shared util | **MEDIUM** | — | **OPEN** — fix: extract `_build_content_disposition` from `pdf_urls.py` to shared util, ~30min |
| R-51 | API auth | `document_types.py:33 GET /api/v1/document-types` — no auth, public read-only metadata (`type`, `name`, `category`, `risk_level`, `language`, `jurisdiction`) | EXECUTED | `document_types.py:33`; live curl 200 (E104) | Public metadata exposure; not sensitive | **LOW** | — | **OPEN** — fix: add optional auth or explicit `Depends(get_current_user)` if policy requires, ~5min |
| R-52 | Concurrent run | `playbook_runs.py:297 rebuild_playbook_and_rerun` — same class as R-33: creates Run via `run_repo.create()` without concurrent guard on a second user-facing endpoint | STATIC + EXECUTED | `playbook_runs.py:297`; E106 | Same as R-33 for rebuild endpoint; **worse**: without rollback, race could leave orphan PlaybookVersion + dangling `deal.playbook_version_id` (atomicity violation) | **CLOSED** (was not in v1.4) | try/except IntegrityError around create; `await db.rollback()` mandatory (reverts new_playbook + deal.playbook_version_id reassignment); `deal_tenant_id_str` cached before rollback (MissingGreenlet fix); 409 + `X-Active-Run-Id`; commits `f46f6ec` + `e1325f9`; DB guard inherited from R-33 migration | **CLOSED** (E106) — 2026-10-26 |
| R-53 | Test gap | Unit tests for R-33/R-52 use `MagicMock` for `deal` (tenant_id as plain attribute, not ORM lazy loader) and `AsyncMock` for `db.rollback` (doesn't expire ORM instances). MissingGreenlet bug (found during dev integration test) not caught by unit tests — only by manual curl race on dev | STATIC + EXECUTED | `tests/api/test_run_concurrent_guard.py` (4/4 passed); E106 | Future ORM-expiration bugs after rollback could slip through unit tests; integration test with real async DB needed | **LOW** | Manual curl race test as safety net (E106); future integration test suite | **OPEN** — real async DB integration test deferred (test DB infra not present in repo) |
| R-45 | Tests / QA | `test_leakage_repro.py` fixture performs unconditional `DELETE FROM audit_logs` on shared `mas_dd`; wipes all 9283 pre-existing audit records on every run, no scope by tenant_id or test marker | STATIC → EXECUTED | `pytest` (E101) output: 9283 audit_logs before, 1 after (test itself creates 1); backup `/tmp/audit_logs_backup_20261026-121932.sql` (5.3 MB) | Destroys forensic evidence on shared DB; not a runtime bug; no customer impact in production (test DB only) | **LOW** | Manual backup before run (optional) | **OPEN** — recommendations: (a) scope DELETE by `tenant_id IN (test_tenant_ids)`; (b) require `TEST_DATABASE_URL` separate from dev; (c) use transaction rollback instead of DELETE |
| R-46 | Deploy | Q6 fix (`--proxy-headers --forwarded-allow-ips=127.0.0.1`) applied to live `/etc/systemd/system/` (E75) but NOT to versioned `deploy/systemd/steloom-demo-backend.service` (last commit `80f8d60` 2026-08-10). Next deploy would revert Q6. | CONFIRMED → CLOSED | `diff deploy/systemd/... /etc/systemd/...`; `git log` Aug 10 (E103) | Rate limit regresses to shared-IP bucket (5/min total); 429 for all users | **HIGH** → CLOSED | (a) Q6 committed to versioned unit (commit `3bd6beb`); (b) `verify_systemd_units_contain_q6()` pre-flight aborts on regression; (c) verified pre- and post-deploy 5×401+2×429 | **CLOSED** (E103) — 2026-10-26 |

**Not claimed:** no "no vulnerabilities"; no "safe"/"production-ready"/"enterprise-grade"; no compliance claim.

## 7. Statement vs observed

| # | Statement | Observed | Impact | Status |
|---|---|---|---|---|
| S-01 | Master-prompt: "MVP with single document" | Multi-doc orchestrator, per-doc plan, segments | Scope larger | Owner-intent |
| S-02 | "pilots without formal measurements" | `tests/benchmark/`, `GATE_*` configs | Reproducibility unclear | Owner-intent |
| S-03 | "multi-doc ≠ cross-document reasoning" | `DocumentSegment` intra-file; `document_families` | Cross-doc reasoning not confirmed | Owner-intent |
| S-04 | `pipeline_strategy` depends only on model | Code confirms | Playbook change doesn't trigger FULL_RERUN | Owner-intent accepted |
| S-05 | `cell_state` includes `not_applicable` | Builder never produces | Contract stale | Update doc |
| S-06 | `execution_status` values listed | Builder normalizes to 6 values | Missing in doc | Update doc |
| S-07 | No risk fields in contract | `cell_risk_level`, `top_risk_*` present | Undocumented | Update doc |
| S-08 | `exports.py` docstring "no role check" | Code checks | Docstring stale | Update |
| S-09 | `AUDIT_FINAL`: "PRODUCTION, FAIL:0" | Playbook YAML only | Misleading at app level | Clarify |
| S-10 | HANDOVER §1: `d692e18` | Actual `f22e3ba`; 182 files/+160k/−54k | HANDOVER stale | Enumerate |
| S-11 | Demo `git rev-parse HEAD` = deployed | rsync without git commit | `git rev-parse HEAD` in demo invalid | Fix deploy script |

## 8. Owner decisions (closed 2026-10-26)

| Q | Decision |
|---|---|
| Q3 | JWT revocation — ACCEPTED + PLANNED. TTL 8h; gap covers deactivation, demotion, password change. Plan: `password_changed_at` + TTL 30min + refresh + re-issue (~8h). |
| Q4 | PII reveal `editor` — ACCEPTED + PLANNED. Editor verifies LLM results on original. Pre-audit mandatory. Plan: rate limit + `can_reveal_pii` flag + confirm dialog (~5h). |
| Q5 | Audit scope — PARTIALLY ACCEPTED + PLANNED. 40+ write actions audited. Gaps: login, upload-id, download, admin-users (~6h). `/alerts` and read-only — intentionally not audited. |
| Q6 | `--proxy-headers` — FIXED 2026-10-26T10:46 UTC (E75). Verified: `5×401 + 2×429` + journal warning with identity. |
| Q9 | Prompt injection — FIXED 2026-10-26 (E97). Compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line applied to `generic_presence.txt`, `classify_document.txt`, `clause_detection.txt`. Smoke test (PromptLoader) + token budget check (E98): `fragment_budget=7756` at `LLM_CONTEXT_LIMIT=12288`, overhead 32.8%. Residual LOW: delimiter escape not sanitized; full closure via `_render_prompt` (~2h, deferred). |

## 9. Open questions

**0 open.** All 23 identified questions resolved: 5 by owner decisions (§8), 13 by code/verification, 5 by explicit ACCEPTED/PLANNED decisions, plus follow-up findings (R-40, R-41, R-42, R-43, R-44, R-45) either ACCEPTED, CLOSED, or LOW.

For the record — closed list:
- Q1 (HEAD), Q2 (demo HEAD), Q7 (unique constraint), Q8 (temp ZIP), Q10 (`_truncated`), Q11 (VARCHAR — actually 50, closed), Q12 (backup rotation), Q13 (PII key rotation), Q14 (rollback), Q15 (`QualityGateError`), Q16 (worker `/metrics`), Q17 (mode C alert), Q18 (`AUDIT_FINAL` scope), Q19 (commits between HANDOVER and HEAD) — CLOSED by evidence.
- Q3, Q4, Q5, Q9 — CLOSED by owner decision (§8).
- Q6 — CLOSED by fix + verification (E75).
- R-42 (`MAX_REASONABLE_SEGMENTS`) — CLOSED by `segmenter.py` inspection.
- R-43 (`anchor_uid`) — LOW dormant; no producer found.
- R-44 (test fixture drift) — CLOSED 2026-10-26 (E100).
- R-45 (test isolation — audit_logs wipe) — OPEN LOW; documented as QA concern.

## 10. Priorities

**Before external test access:**
1. R-29 — rotate MinIO root credentials.
2. R-27 — update `dd_grid_v1_contract.md`.
3. R-38 — ✅ **CLOSED** (E103): `.deploy-meta.json` auto-gen; deployed identity traceable.
4. R-40 — remove `handle /storage/*` from Caddyfile (defense-in-depth; not blocking).

**Before completing technical DD:**
5. R-03 — PII reveal rate limit.
6. R-01 — JWT revocation plan execution (~8h).
7. R-02 — audit gaps (login, upload-id, download, admin-users; ~6h).
8. R-18 — `_truncated` badge (~3h).
9. R-22 — CI test workflow (~2h).

**After the round:**
10. R-10 — PII key rotation.
11. R-14 — `password_changed_at` / `last_login_at`.
12. R-26 — `prompts/README.md`.
13. R-28 — rollback script.
14. R-39 — ✅ **CLOSED** (E103): `rotate_backups()` 30d + keep 10; 42→12 dirs.
15. R-30 — incremental ADRs.
16. R-31 — audit event on `QualityGateError`.
17. R-34 — mode C alert.
18. R-32 — worker `/metrics`.
19. R-05 — rate limiter fallback.
20. R-08 — catch `IntegrityError` in call sites.
21. R-09 — remove dead `_safe_truncate(20)`.
22. R-17 residual — optional sanitization in `_render_prompt` for delimiter-escape closure (~2h).
23. R-45 — scope `test_leakage_repro.py` DELETE by tenant_id or require `TEST_DATABASE_URL` separate from dev (~1h). Prevents accidental audit_logs wipe on shared dev.

**Accepted / low priority:** R-11, R-12, R-15, R-16, R-17 residual (LOW), R-19, R-20, R-21, R-23, R-24, R-25, R-33, R-35, R-36, R-40, R-41, R-43 (dormant), R-45 (LOW, mitigated by backup procedure).

---

*End of QUALITY_AND_RISKS. Audited baseline `f22e3ba`; HEAD at completion `e1325f9`. Demo deployed at `e1325f9` 2026-10-26T17:13 UTC (E103, E106). Threat model v1.1 (`internal/THREAT_MODEL.md`) — 18 threats, E104/E106. **51 risks in final status:** CLOSED — R-03/R-07/R-33/R-38/R-39/R-44/R-46/R-49/R-52; OPEN — R-50 MEDIUM (content-disposition), R-51 LOW (document_types public GET), R-24 LOW-MEDIUM (magic fail → VALID), R-53 LOW (test gap for ORM expiration), R-45 LOW (test isolation). 0 HIGH open. 0 open owner questions.*
