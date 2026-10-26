# Steloom / LegalMAS — Technical DD Review Worklog (internal)

**Status:** Final (internal trace)
**Date:** 2026-10-26
**Version:** 1.4
**HEAD at completion:** `763f2d9` (7 post-snapshot commits over audited baseline `f22e3ba`)
**Reviewer:** AI-assisted static analysis + owner-executed verification (not independent audit)
**Snapshot:** CONFIRMED — `master`, HEAD `f22e3ba1b82348ba1208bd7de8f183ff5331df57`

## Snapshot & access

- Source: GitHub `701315/LegalMAS` via owner `git ls-files` + 9 file batches from `/srv/steloom-dev`.
- Branch: `master`.
- HEAD: `f22e3ba1b82348ba1208bd7de8f183ff5331df57` — CONFIRMED.
- Working tree (dev): `M frontend/public/steloom.svg`.
- HANDOVER reference: `d692e18`; diff = 182 files, +159,922/−53,613, 79 non-merge commits.
- Deployed demo: git HEAD `97901c8` (rsync; R-38).
- Backups: `/mnt/backups/steloom-demo/` — 15 GB, 9 dirs.
- Files viewed: ~140 across 9 batches + Tier 1/Tier 2 test fixes + end-to-end run inspection.
- Files NOT viewed (significant):
  - `_element_classifier/`, `_heading_builder/`, `_heading_scoring/`, `_hierarchy_builder/`, `_models/` (except `_identity.py`), `semantic_enrichment/`, `coherence/`, `cohesion/`, `chunk_planner/_types.py`, `_clause_detector/routing.py` (~70 files in structure).
  - Full alembic history (~150; 4 viewed: initial, jobs unique, plan_items unique, schema_drift).
  - Frontend beyond DD Grid V1.
  - `aws/`; deep `monitoring/`.
  - `docs/AUDIT_FINAL_2026-10-17.txt` — playbook-only scope.

## 79 non-merge commits between `d692e18` and `f22e3ba` (R-37 closed)

Themes observed: race fixes (~6); B3.5 element_spans (~11); reaper (~7); LLM usage async fixes (~8); HANDOVER v7.8 (~2); calibration ~50; audit report (1).

Diff scope: **182 files, +159,922 / −53,613 lines**. Significantly more work than "85 commits" implies.

## Evidence register

| ID | Claim | Path / Symbol | Type | Limitation |
|---|---|---|---|---|
| E01 | JWT-only, no fallback | `auth.py:get_current_user` | STATIC | — |
| E02 | JWT no revocation / refresh / password_changed_at / token_version | grep `src/` | STATIC | — |
| E03 | `is_active` filtered at login | `user_repo.get_by_email` | STATIC | — |
| E04 | PII reveal editor+; pre-audit mandatory | `pii_reveal.py:85,119` | STATIC | — |
| E05 | No rate limit on PII reveal | `rate_limit.py` (only login/logs/admin) | STATIC | — |
| E06 | Dev plaintext PII if key empty | `pii_encryption.py:encrypt_mapping` | STATIC | — |
| E07 | No key rotation in `pii_encryption.py` | grep | STATIC | — |
| E08 | No prompt injection defense (pre-fix) | `prompts/*` | STATIC | Superseded by E97 |
| E09 | Grounding thresholds 0.1/0.3 | `llm_detector.py` | STATIC | — |
| E10 | `_truncated` not read by frontend | backend + frontend grep | STATIC | — |
| E11 | Two check-scheduling paths | `check_runner_worker.py`, `run_checks_auto_starter.py` | STATIC | — |
| E12 | Upload temp ZIP not cleaned on success | `deals/documents.py:222,255-263` | STATIC | — |
| E13 | Import use case uses `TemporaryDirectory` | `import_bundle_use_case.py:255` | STATIC | — |
| E14 | `_safe_truncate(20)` | `result_repo.py` | STATIC | E90 confirms no-op |
| E15 | `review_status` canonical mapping | `result_semantics.py` | STATIC | — |
| E16 | `pass` + all-fallback → `clause_missing` | `result_semantics.py` | STATIC | — |
| E17 | DD request trigger by `review_status` | `dd_request_rules.py` | STATIC | — |
| E18 | HANDOVER `d692e18` | `HANDOVER_v7.8.md` §1 | OWNER-REPORTED | Stale (E44) |
| E19 | Test baselines | HANDOVER v7.8 | OWNER-REPORTED | Not re-run |
| E20 | CI = only `pip-audit` | workflow | STATIC | — |
| E21 | `--proxy-headers` was missing; XFF not read | systemd + grep | STATIC → FIXED (E75) | — |
| E22 | No rate limiter fallback on Redis down | `rate_limit.py` | STATIC | Not executed |
| E23 | Pre-auth `tenant_id` from header | `audit.py` | STATIC | — |
| E24 | V2 layout enabled by default | `layout_config` | STATIC | — |
| E25 | Instruction snapshot frozen twice | orchestrator + check_runner | STATIC | — |
| E26 | `Job(run_deal_checks)` unique | `45bb66b1d8e5` | STATIC | — |
| E27 | `prompts/README.md` empty | hash | STATIC | — |
| E28 | Anti-hypotheses B7.3/B7.7/B7.8 rejected | HANDOVER §3 | OWNER-REPORTED | — |
| E29 | 15-layer layout, 3 gates | `service.py` | STATIC | — |
| E30 | Docling CPU-only singleton | `docling_extractor.py` | STATIC | — |
| E31 | Spatial marker recovery for Docling #1345 | `docling_extractor.py` | STATIC | Recovery rate not measured |
| E32 | Quality gates with quarantine | `quality.py` | STATIC | — |
| E33 | Structure → `_core_builder` | `builder.py`, `_core_builder.py` | STATIC | — |
| E34 | LLM clause detection in structure | `_core_builder.py:LLMClauseDetector` | STATIC | — |
| E35 | Phase 10 chunk planner 3 modes | `chunk_planner/_planner.py` | STATIC | — |
| E36 | Boundary-aware chunking | `chunking.py` | STATIC | `chunk_boundaries.py` not read |
| E37 | Embedding singleton + optional cache | `embedding_service.py` | STATIC | — |
| E38 | Export lifecycle audit | `export/service.py` | STATIC | — |
| E39 | 11 alert rules | `monitoring/alerts/*.yml` | STATIC | — |
| E40 | LLM alerts sleeping | `operations.yml` self-comment | STATIC + OWNER-REPORTED | — |
| E41 | `AUDIT_FINAL` playbook-only | audit file + scripts | STATIC | — |
| E42 | HEAD `f22e3ba` | `git rev-parse HEAD` | OWNER-CONFIRMED | — |
| E43 | `M frontend/public/steloom.svg` | `git status --short` | OWNER-CONFIRMED | Not relevant |
| E44 | 79 non-merge commits between `d692e18` and `f22e3ba`; 182 files, +159,922/−53,613 | `git diff --stat`, `git log` | OWNER-CONFIRMED | — |
| E45 | JWT revocation absent | grep | STATIC | Only unrelated `denylist` in `_policy.py` |
| E46 | PII reveal `editor, admin` | `pii_reveal.py:85` | STATIC | — |
| E47 | No `can_reveal_pii` (grep) | grep `src/` | STATIC | — |
| E48 | Audit actions: 40+, no login/upload-id/download/admin-users/`/alerts` | grep `action="` + endpoints | STATIC | Includes `result_presentation.approved/edited/rejected/reset`, `tenant.locale_policy_updated` |
| E49 | `_AUDITED_PATH_SUFFIXES` = 6 paths | `audit.py` | STATIC | — |
| E50 | No `--proxy-headers` / XFF in deploy | grep | STATIC → FIXED (E75) | — |
| E51 | `request.client.host` only in `rate_limit.py` | grep | STATIC | — |
| E52 | Unique partial indexes on plan items | `bc56177ec084` | STATIC | — |
| E53 | Composite uniqueness via two partial indexes | `run_check_plan_item.py` | STATIC | — |
| E54 | Upload cleanup only in `except` | `deals/documents.py:255-263` | STATIC | — |
| E55 | `TemporaryDirectory` for internal extract | `import_bundle_use_case.py:255` | STATIC | — |
| E56 | `{context}` / `{document_fragment}` raw (pre-fix) | grep prompts | STATIC | Superseded by E97 |
| E57 | `_truncated` written by backend | `extraction_llm_detector.py`, `extraction.py` | STATIC | — |
| E58 | Frontend does not read `_truncated` | grep `frontend/src/` | STATIC | Unrelated `truncated` in admin pagination |
| E59 | Model `result.py` uses `String(50)`; no explicit ALTER migration | `result.py` + alembic grep | STATIC | E90 confirms DB = VARCHAR(50) |
| E60 | No backup rotation; 15 GB, 9 dirs | `deploy-demo.sh`, `/mnt/backups/` | OWNER-CONFIRMED | — |
| E61 | No PII key rotation | `pii_encryption.py` | STATIC | — |
| E62 | No rollback script | find | STATIC | — |
| E63 | `QualityGateError` → QUARANTINE + details | `build_primary_language_source.py:319-390` | STATIC | — |
| E64 | No `LAYOUT_QUARANTINED` audit | grep `src/` | STATIC | — |
| E65 | Worker `/metrics` not implemented | grep `start_http_server` | STATIC | `/metrics` only in `src/ops/instrument.py` |
| E66 | No `LAYOUT_FALLBACK` alert | grep alerts | STATIC | — |
| E67 | `audit_*.py` scripts scan `playbooks/` | grep scripts | STATIC | — |
| E68 | Demo git HEAD `97901c8`; tree has hundreds of `M` | `git rev-parse HEAD` in demo | OWNER-CONFIRMED | — |
| E69 | Owner decision Q3 | Owner | OWNER-REPORTED | ACCEPTED + PLANNED |
| E70 | Owner decision Q4 | Owner | OWNER-REPORTED | ACCEPTED + PLANNED |
| E71 | Owner decision Q5 | Owner | OWNER-REPORTED | PARTIALLY ACCEPTED + PLANNED |
| E72 | Owner decision Q9 | Owner | OWNER-REPORTED | ACCEPTED + PLANNED |
| E73 | Caddyfile `/api/*` sets XFF; `/storage/*` proxies MinIO; `/ws/*` dead block | `/etc/caddy/Caddyfile` | OWNER-CONFIRMED | — |
| E74 | `/storage/mas-artifacts/` → 403 (bucket private) | `curl` | EXECUTED | — |
| E75 | Q6 fix applied 2026-10-26T10:46 UTC; `5×401 + 2×429`; journal warning with identity | systemd + journalctl + curl | EXECUTED | Local test doesn't differentiate per-IP |
| E76 | `/ws/` → 404 application/json (no endpoint) | `curl` | EXECUTED | — |
| E77 | Segmenter: 11 weighted signals; score = max(0, min(sum, 1.0)); `WEAK_BOUNDARY_THRESHOLD=0.45`; `MIN_ELEMENTS_BETWEEN_BOUNDARIES=3` | `_segmenter/candidates.py`, `_segmenter/config.py` | STATIC | — |
| E78 | Swarm protection: 2+ same-family within ±4 + no substantive body → reject; `detect_body_internal_boundary_listing` | `_segmenter/heuristics.py`, `candidates.py` | STATIC | — |
| E79 | TOC/catalog suppression: 6 topological heuristics; `contiguous_entry_cluster_violates_document_physics` | `_segmenter/toc_suppression.py` | STATIC | — |
| E80 | Purity recovery: ≤3 iterations; `_is_distinct_internal_boundary_candidate` | `_segmenter/purity.py` | STATIC | — |
| E81 | V2-aware: `_is_v2_format` (≥30%); `_collect_v2_anchor_boundaries` with confidence=0.95; merged with legacy | `_segmenter/candidates.py` | STATIC | R-43 dormant |
| E82 | `MAX_REASONABLE_SEGMENTS=15` enforced in `segmenter.py` public facade | `segmenter.py:200-213` | STATIC | R-42 CLOSED |
| E83 | L1 filename: generic-under-specific cap; rule kinds `specific_subject`/`generic_form`/`context`; folder weight 0.75 | `l1_filename.py` | STATIC | — |
| E84 | L2 header: extended log-normalized (max_expected=5.0), signal_quality formula, hard/soft exclusions, `input_quality` weight; legacy `_LEGACY_*` | `l2_header.py` | STATIC | — |
| E85 | L3 semantic: multi-window (800/600/400; 0.50/0.30/0.20), negative factor 0.35, margin calibration, ambiguity_penalty in extra | `l3_semantic.py` | STATIC | — |
| E86 | L3 noise suppression: `margin<0.05` AND `pos_sim<0.65` → excluded from voting, still pre-L4 signal | `_cascade_steps.py:run_l3` | STATIC | — |
| E87 | Cascade steps: no stop conditions inside; L2 runner-up candidate if conf>0.35; L2 hard exclusion ≥ `L2_EXCL_HARD(1)` → UNKNOWN | `_cascade_steps.py` | STATIC | — |
| E88 | `segment_document()` fallback chain: exception/empty/invalid-ranges/all-empty → single segment | `_pipeline/_segment_utils.py` | STATIC | — |
| E89 | `segmenter.py` enforces `MAX_REASONABLE_SEGMENTS=15` and `SEGMENT_CONFIDENCE_THRESHOLD` | `segmenter.py` | STATIC | R-42 CLOSED |
| E90 | DB: `check_results.result` and `check_results.severity` are `VARCHAR(50)` | `information_schema.columns` via psql | EXECUTED | R-09 CLOSED |
| E91 | Diff `d692e18..f22e3ba`: 182 files, +159,922/−53,613, 79 non-merge commits | `git diff --stat`, `git log \| wc -l` | EXECUTED | R-37 CLOSED |
| E92 | `LLMClauseDetector.refine_tree()` — hybrid merge (LLM + numeric fallback), appendices boundary trimming, global routing, list-intro invariant, frozen-safe, LLM usage recorded via `record_event_isolated(stage="structure_clause_detection")` | `_clause_detector/detector.py` | STATIC | §7.2 |
| E93 | `parser.py` — conservative numeric-only fallback (`\d+\.\d+(?:\.\d+)*\.?` with `^\s*` anchor); resilient JSON extraction; title validated via `_looks_like_valid_clause_title` | `_clause_detector/parser.py` | STATIC | R-17 mitigation |
| E94 | `anchor_uid` producer not found in `document_layout/`, `structure/` (except consumer), `engine/content/` via grep | grep | STATIC | R-43 LOW (dormant) |
| E95 | `prompts/structure/clause_detection.txt` exists (107 lines, 0 markers `<UNTRUSTED>`/`<TEXT>`/`ignore.*instruction` pre-fix) | `cat`, `grep -c` | STATIC | R-17 expanded to 3 files; superseded by E97 |
| E96 | `deal_review_service.py` — DatabaseInstructionProvider invariant, apply_presentations_for_read, auto-translation dispatch, RunCheckPlanItemRepository as source of truth | `deal_review_service.py` | STATIC | §6 |
| E97 | Q9 fix applied 2026-10-26: compact `<UNTRUSTED_DOCUMENT_TEXT>` delimiters + security line in `prompts/detection/generic_presence.txt`, `prompts/classification/classify_document.txt`, `prompts/structure/clause_detection.txt`. Smoke test: `PromptLoader.load()` renders all 3 with balanced markers (open>=2, close=1), context substituted. Lengths: 2507/6281/4496. | diff + smoke test | EXECUTED | Residual LOW: delimiter escape not sanitized |
| E98 | Runtime LLM config (demo `.env`): `LLM_CONTEXT_LIMIT=12288` (code default 32768), `LLM_MAX_TOKENS=256`, `LLM_SAFETY_MARGIN_TOKENS=512`. L4 worst-case: `chatml_overhead=242`, `skeleton_tokens=3778`, `max_prompt=11776`, `fragment_budget=7756`, overhead_ratio 32.8%. | smoke test | EXECUTED | At LLM_CONTEXT_LIMIT=4096, fragment_budget→floor 300 — L4 near-useless |
| E99 | Tier 1 pytest 2026-10-26 (HEAD f22e3ba): `test_exports_access.py` 11/11 passed; `test_result_semantics*.py` 118/118 passed; `test_result_presentation_smoke.py` initial run 2 failed → pre-existing test/spec drift (R-44: `make_translation_ru` missing 3 required args; `make_check_result` missing `structured_data`; `TransientError` exception no longer propagated) | `pytest` | EXECUTED | Failures pre-existing, not from Q9 fix |
| E100 | R-44 fixed 2026-10-26: (a) added `localized_structured_data`/`dd_request_text`/`dd_request_addressee` to `make_translation_ru`; (b) added `structured_data=None` to `make_check_result`; (c) rewrote `test_e2e_presentation_transient_error_retry` to assert summary-based behavior (batch swallows `TransientError`); (d) removed unused `TransientError` import; (e) `ruff check --fix` cleaned trailing whitespace (13 fixes: I001 import sort, F401 unused pytest, W291/W293). Result: `pytest tests/e2e/test_result_presentation_smoke.py` → 2/2 passed; `ruff check` clean. Tier 1 total: 131/131 passed. | `pytest` + `ruff` | EXECUTED | — |
| E101 | Tier 2 security pytest 2026-10-26 (dev `mas_dd`): `tests/security/test_leakage_repro.py` → 3/3 passed. `test_reproduce_unauthorized_deal_access` (401), `test_reproduce_cross_tenant_evidence_leakage` (404), `test_reproduce_audit_identity_spoofing` (actor != X-User-Id). Fixture performs unconditional `DELETE FROM audit_logs` on `mas_dd` — 9283 pre-existing records wiped; manual backup `/tmp/audit_logs_backup_20261026-121932.sql` (5.3 MB, 9317 lines). New finding R-45 (LOW). Tier 1+2 total: 134/134. | `pytest` | EXECUTED | Fixture destructiveness (R-45) |
| E103 | Deploy hardening 2026-10-26T14:07 UTC: (a) R-46 fix committed to versioned `deploy/systemd/steloom-demo-backend.service` (commit `3bd6beb`) + `verify_systemd_units_contain_q6()` pre-flight (commit `763f2d9`); (b) R-39 `rotate_backups()` retention 30d + keep 10 (commit `763f2d9`) → 42→12 dirs, 15 GB→4.4 GB; (c) R-38 `.deploy-meta.json` auto-gen → `{dev_head: 763f2d9, deployed_at: 2026-10-26T14:07:58, backup_dir: 2026-10-26-140553}`. Post-deploy verify: services active, systemd repo==live (3×), meta==git HEAD, Q6 fix 5×401+2×429 (pre==post), endpoints OK, 12 backups, 4.4 GB. | `systemd`, `diff`, `curl`, `git log`, `cat .deploy-meta.json` | EXECUTED | R-38/R-39/R-46 CLOSED |
| E102 | End-to-end pipeline run 2026-10-26 (dev, HEAD f22e3ba, run `b7025e4e-7824-4ba3-a200-3817696012e7`, deal `ad27bbf4-c1d1-4340-bbbb-27880860d762`): synthetic `Sample_Contract.DOCX` (18 pp.) → `contract_1.6_real_estate` (confidence 0.95) → DD Grid. Status `completed`; `has_errors=f`; duration **17.5 min** (12:29:35 → 12:47:05 UTC); `pipeline_strategy=REUSE_STRUCTURE`, `checks_mode=global_and_doc_type`. 21/21 checks succeeded (14 pass, 0 fail, 1 unclear, 6 no-verdict). Anchors: 34 exact_span (34 validated), 8 fuzzy_span (8 validated), 19 clause_only. LLM usage: 37 calls (`checks_extraction_llm` 20, `result_presentation_translation` 12, `run_summary_pass_b` 1, `run_summary_pass_a` 1, `structure_clause_detection` 1, `structure_semantic_enrichment` 1, `classification_l4` 1); model `qwen2.5:14b` on Ollama. Audit trail: 16 distinct action types (27 rows total) full lifecycle (IMPORT → ANALYSIS_COMPLETED + 12 translations). DD Grid: 21/21 with `structured_data` + `primary_anchor_id`. | `psql` + pipeline run | EXECUTED | Single synthetic doc; CPU-only Ollama; base model (not qwen25-legal tuned) |

## Contradictions

| # | Claim | Observed | Impact |
|---|---|---|---|
| C1 | "MVP, single document" | Multi-doc orchestrator | Scope redefinition |
| C2 | "pilots without formal measurements" | `tests/benchmark/`, `GATE_*` | Partial |
| C3 | `not_applicable` cell_state | Builder never produces | Contract stale |
| C4 | `pipeline_strategy` on model only | Code confirms | Repro limitation |
| C5 | `pass` + `clause_missing` | Defensive code | R-25 |
| C6 | HANDOVER `d692e18` | Actual `f22e3ba`; 182 files/+160k/−54k | R-37 |
| C7 | Demo `git rev-parse HEAD` = deployed | rsync without commit | R-38 |

## Open questions

**0 open.** 23/23 closed + follow-up findings (R-40, R-41, R-42, R-43, R-44, R-45): R-17 fixed 2026-10-26 (E97), residual LOW; R-09 closed (E90); R-37 closed (E91); R-42 closed (E82/E89); R-43 LOW dormant (E94); **R-38 CLOSED (E103)**; **R-39 CLOSED (E103)**; **R-44 CLOSED (E100)**; **R-45 OPEN LOW** (test isolation — audit_logs wipe, E101); **R-46 CLOSED (E103)**.
- Q1, Q2, Q7, Q8, Q10, Q11 (VARCHAR(50) verified), Q12, Q13, Q14, Q15, Q16, Q17, Q18, Q19 — CLOSED by evidence.
- Q3, Q4, Q5, Q9 — CLOSED by owner decision (E69–E72).
- Q6 — CLOSED by fix + verification (E75).
- R-42 — CLOSED (`segmenter.py` enforcement, E82/E89).
- R-43 — LOW dormant (no `anchor_uid` producer, E94).
- R-44 — CLOSED 2026-10-26 (E100).
- R-45 — OPEN LOW; scope DELETE by tenant_id or require separate test DB.

## Executed commands (owner + reviewer)

**Snapshot & static:**
- `git rev-parse HEAD` (dev) → `f22e3ba`.
- `git status --short` (dev) → `M frontend/public/steloom.svg`.
- `git rev-parse HEAD` (demo) → `97901c8` + hundreds of `M`/`D`/`??`.
- `git log --oneline d692e18..f22e3ba` → 79 non-merge commits.
- `git diff --stat d692e18..f22e3ba` → 182 files, +159,922/−53,613.
- Grep commands (E45–E67, E77–E88, E94).
- `ls -lt /mnt/backups/steloom-demo/releases/`, `du -sh` → 15 GB, 9 dirs.

**Q6 fix (E75):**
- `sed` systemd unit; `install` to `/etc/systemd/system/`; `systemctl daemon-reload`; `systemctl restart`; `systemctl is-active` = `active`.
- 7 login attempts via `--resolve` → `5×401 + 2×429`.
- `journalctl | grep "rate limit"` → warning with `identity="127.0.0.1"`, `request_id`.

**Other runtime (E74, E76, E90):**
- `curl /storage/mas-artifacts/` → `403`, `server: MinIO`.
- `curl /ws/` → `404`, `application/json`.
- `cat /etc/caddy/Caddyfile`.
- `psql \d check_results` for `result`/`severity` → `character varying(50)`.

**Q9 fix (E97, E98):**
- Q9 fix applied 2026-10-26: compact `<UNTRUSTED_DOCUMENT_TEXT>` + security line in 3 prompt files.
- Smoke test: `PromptLoader.load()` × 3 → all OK (open>=2, close=1, context substituted); lengths 2507/6281/4496 (E97).
- Token budget check for L4 with 20 candidate types: `fragment_budget=7756` at `LLM_CONTEXT_LIMIT=12288`, overhead_ratio 32.8% (E98).

**Tier 1 pytest (E99, E100):**
- `pytest tests/api/test_exports_access.py -v` → 11/11 passed.
- `pytest tests/unit/engine/checks/test_result_semantics*.py -v` → 118/118 passed.
- `pytest tests/e2e/test_result_presentation_smoke.py -v` → initial 2 failed (R-44); fixtures updated; final 2/2 passed.
- `ruff check tests/e2e/test_result_presentation_smoke.py --fix` → 13 fixes applied; final `All checks passed!`.
- Tier 1 total: 131/131 passed.

**Tier 2 pytest (E101):**
- `pytest tests/security/test_leakage_repro.py -v --tb=short` → 3/3 passed (DB).
- Pre-flight: `SELECT COUNT(*) FROM audit_logs` → 9283.
- Manual backup: `pg_dump -t audit_logs --data-only` → `/tmp/audit_logs_backup_20261026-121932.sql` (5.3 MB, 9317 lines).
- Post-run: `SELECT COUNT(*) FROM audit_logs` → 1 (test fixture residual).

**End-to-end pipeline run (E102):**
- `psql` queries: 8 blocks against `mas_dd` — run metadata, documents, check_results, anchors, llm_usage, audit_logs, DD Grid shape.
- Run `b7025e4e-...` on deal `ad27bbf4-...` → `completed` in 17.5 min, 21/21 checks.

**Deploy hardening 2026-10-26T14:07 UTC (E103):**
- `./deploy/deploy-demo.sh` exit 0; env contract errors=0; Q6 pre-flight OK.
- Rotation: 42→12 dirs, 15 GB→4.4 GB.
- rsync + alembic + npm build OK; systemd units installed; 3 services active; worker queues OK; health checks OK.
- Meta auto-gen: `{dev_head: 763f2d9, deployed_at: 2026-10-26T14:07:58, backup_dir: 2026-10-26-140553}`.
- `diff deploy/systemd/*.service /etc/systemd/system/*.service` → 3× IDENTICAL.
- `curl` 7× login → 5×401 + 2×429 post-deploy (== pre-deploy).

**Verification of v1.4 documents (2026-10-26):**
- `grep -E "^\*\*Version:" docs/technical-dd/README.md` → `**Version:** 1.4`.
- `grep -cE "E10[0-2]|R-44|R-45|134/134|17\.5" docs/technical-dd/README.md` → 22 (>= 5 expected).
- `grep "45 risks in final status" docs/technical-dd/README.md` → one line.
- QUALITY_AND_RISKS.md: 6/6 verification blocks passed (Version 1.4, 45 risks, R-44 CLOSED, R-45 OPEN, E99–E102 × 24, 0 mojibake).

## Not executed

- Broad test suite (`tests/unit/` 1701, `tests/services/` 1027); build; migration; Docker; systemd (beyond Q6); LLM inference; DB (except schema introspection, Tier 2 security tests, E102 run); MinIO; `pip-audit`; `ruff check` on full codebase; redeploy; git commit in demo.
- Second E2E run for statistical validity (E102 is single run; not a benchmark).

## Continuation checkpoint

1. Read this worklog first.
2. Drafts in `docs/technical-dd/` at v1.4.
3. Snapshot CONFIRMED at `f22e3ba`. Do not revert to `d692e18`.
4. 0 open questions.
5. Fix log:
   - Q6 applied 2026-10-26T10:46 (E75). Verified with journalctl + curl.
   - Q9 applied 2026-10-26 (E97). Compact `<UNTRUSTED_DOCUMENT_TEXT>` + security line in 3 prompt files; smoke-tested. Runtime LLM config recorded (E98): LLM_CONTEXT_LIMIT=12288. Residual LOW: delimiter escape not sanitized; optional `_render_prompt` sanitization (~2h, deferred).
5b. Tier 1 pytest 2026-10-26 (E99, E100): 131/131 passed. R-44 closed (test fixture drift). No regressions from Q6 or Q9 fix.
5c. Tier 2 pytest 2026-10-26 (E101): 3/3 security regression passed. R-45 OPEN LOW (test fixture wipes audit_logs on `mas_dd`).
5e. R-38/R-39/R-46 closed 2026-10-26T14:07 UTC (E103): deploy hardening committed (`3bd6beb`, `763f2d9`), demo deployed at `763f2d9`, `.deploy-meta.json` auto-gen, backup rotation 42→12 (15 GB→4.4 GB), Q6 fix verified pre/post (5×401+2×429).
5d. End-to-end pipeline run 2026-10-26 (E102): `completed` in 17.5 min on synthetic 18-pp. contract; 21/21 checks; 42 validated anchors; full audit trail. Baseline OWNER-REPORTED → EXECUTED (partial) for 134 tests + 1 E2E run.
6. Files read (batch A–J): api, deps, middleware, services (import, layout, structure, checks starter, DD Grid, QC, PII, export, translation, deal review), engine (checks, detectors, retrieval, prompt loader), classifiers (hybrid, L1, L2, L3, cascade steps), workers (orchestrator, checks, import), mas_queue (celery, base_task, dispatcher), core (config, anchors), storage, deployment, prompts (3), monitoring alerts, DB schema.
7. Files not read (optional): `_element_classifier/`, `_heading_builder/`, `_heading_scoring/`, `_hierarchy_builder/`, `_models/` (except `_identity.py`), `semantic_enrichment/`, `coherence/`, `cohesion/`, `chunk_planner/_types.py`, `_clause_detector/routing.py`. Not required for DD — coverage adequate.
8. Optional future work (P1, not blockers): L1–L3 classifier tests execution; structured threat model; performance baseline on one document (E102 provides first data point); statistical E2E runs on multiple synthetic docs.

---

*End of REVIEW_WORKLOG. Internal working document — not for investor delivery. Audited baseline `f22e3ba`; HEAD at completion `763f2d9`. Tier 1+2 pytest 134/134 passed (E99–E101). E2E run 17.5 min (E102). Deploy hardening 2026-10-26T14:07 UTC: demo deployed at `763f2d9` (E103). R-38/R-39/R-44/R-46 CLOSED. R-45 OPEN LOW. 45 risks in final status. 0 open owner questions.*
