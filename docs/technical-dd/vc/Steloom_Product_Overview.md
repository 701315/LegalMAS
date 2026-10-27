# Steloom / LegalMAS — Product Overview

**Document:** Steloom_Product_Overview
**Version:** 1.1
**Date:** 2026-10-27
**Audience:** tech due diligence
**Snapshot:** audited baseline `f22e3ba`; HEAD at completion `e1325f9` (demo deployed at `e1325f9`, 2026-10-26T17:13:48 UTC)
**Companion to:** `Steloom_Architecture.md` (technical), `Steloom_AI_Quality_and_Limitations.md` (AI honesty), `TECHNICAL_OVERVIEW.md` / `QUALITY_AND_RISKS.md` (audit pack)

Technical detail is in the companion documents. Claims are bounded by code at HEAD `e1325f9`; no capabilities beyond that are attributed to the current product.

---

## 1. Users, buyers, and what the product replaces

**Primary design target:** mid-market in-house legal teams handling a flow of **≥50 new legal documents** through review — ongoing contract / compliance review, not one-off M&A deals.

**Buyer:** General Counsel, Head of Legal Operations, or senior in-house counsel at mid-market companies (typically 200–2000 employees) where legal headcount (2–15 lawyers) is outnumbered by incoming document volume.

**User:** in-house lawyer, paralegal, or legal-ops analyst doing the actual document review.

**Adjacent segments** (same artifact — DD Grid over playbook checks — with different playbooks): law firms (associate-level review), M&A analysts, PE/VC funds (deal diligence) and internal audit and compliance teams. Adjacent, not primary; the product is designed around the mid-market in-house flow.

**Work replaced or accelerated:** the manual first pass of a contract set against a company's rules — checking each document for change-of-control clauses, liability caps, termination grounds, sanctions exposure, IP ownership, and so on — any checks the company could consider applying to the document to review, driven by the lawyer's level of education, experience, and paranoia. That first pass is mechanical but time-consuming; today it is either done by a junior lawyer line by line, or skipped under volume. Steloom produces a structured **DD Grid**: every document × every check, with a verdict, a cited anchor (page / clause / span), and a review status for human sign-off. It does not replace legal judgment — it produces a structured draft a human reviews.

---

## 2. What works today

The end-to-end path is live: **upload → language discovery → layout & PII sanitize → structure → chunks → classify → playbook checks → DD Grid → export**.

Observed end-to-end on a synthetic 18-page contract (E102, 2026-10-26, dev; second run E105 after fixes):

| Aspect | E102 | E105 (post-fix) |
|---|---|---|
| Duration | 17.5 min (GPU: RTX 5060 Ti, 49/49 layers offloaded, qwen2.5:14b) | 15.2 min |
| Checks scheduled / completed | 21 / 21 | 21 / 21 |
| Check results | 14 pass / 0 fail / 1 unclear / 6 no-verdict | same shape |
| Anchors | 42 validated (34 exact_span + 8 fuzzy_span) | 43 validated (35 exact_span + 8 fuzzy_span) |
| LLM calls | 37 | 46 |
| Classification | 0.95 confidence, `contract_1.6_real_estate` | same |

Full lifecycle audited: IMPORT → LANGUAGE_DISCOVERY → ANALYSIS_STARTED → PRIMARY_SOURCE_READY → SANITIZE → CHUNK_BUILD_COMPLETED → CLASSIFY_COMPLETED → STRUCTURE_COMPLETED → LEGAL_UNITS_ENRICHMENT_COMPLETED → ANALYSIS_COMPLETED → result_presentation.

**What a user can do today:** create a deal, upload one or multiple documents, run the pipeline, open the DD Grid, review each cell (verdict + cited anchor + status), apply QC (approve / reject / edit), export to Excel / Word / JSON. Human review is built into the loop: every check result carries a `review_status` and pre-audit; the grid is a draft, not a verdict.

**What is deliberately bounded:** single-document end-to-end is verified; multi-document orchestration exists and is exercised, but the synthetic E2E evidence is single-document. Cross-document reasoning (comparing clauses across documents) is not claimed as a validated capability — cross-document infrastructure is established but not yet fully utilized in the end-to-end evidence.

---

## 3. What is not yet built (vision / roadmap — explicitly not current product)

- **External counterparty and asset verification** — registry integrations (e.g. ЕГРЮЛ, Companies House) to verify counterparties and assets against external data. Not in code.
- **Word add-in** — review inside Word rather than in the web UI. Not in code.
- **Legal Intelligence** — the founder's term for long-term analytical capabilities (cross-deal insights, patterns, trend detection). Not in code; scope to be defined.
- **AI-assisted self-serve playbook composition** — today clients can build playbooks in Playbook Studio by selecting from a library of 900+ checks authored by Steloom's domain experts; AI-assisted composition (like a GPT-style chatbot that drafts a playbook from a compliance matrix) is a roadmap item, not current.
- **Legislation monitoring** — not in code.

None of the above is attributed to the current product. They are listed so the boundary is explicit.

---

## 4. Document formats, languages, doc-types

**Supported formats — 25 extensions** (whitelist `IMPORT_ALLOWED_EXTENSIONS`, validated in `file_validator.py`):

| Category | Extensions |
|---|---|
| PDF | `.pdf` |
| Word | `.docx`, `.doc`, `.docm`, `.rtf`, `.odt` |
| Excel | `.xlsx`, `.xls`, `.xlsm`, `.ods`, `.csv` |
| PowerPoint | `.pptx`, `.ppt`, `.odp` |
| HTML | `.html`, `.htm` |
| Images (scanned docs) | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp`, `.webp`, `.heic`, `.heif` |

Office formats go through an isolated LibreOffice microservice → PDF → layout extraction; images go through OCR. Validation: extension whitelist + magic-byte sniffing + size limit. Known gap (R-24, LOW-MEDIUM): HEIC / WebP magic bytes not checked — a file with `.heic` / `.webp` extension and non-image content passes as `unknown` and relies on the downstream parser. Documented, not hidden.

**Languages:** multilingual pipeline; language discovery is a mandatory precondition (the deal gets a `primary_language`); classification uses language-agnostic embedding signals (BGE-M3) with RU/EN-specific heuristics (to be extended to other languages at a later stage). PII tokenizer role map is RU/EN (R-11, LOW) — role hints for other languages are not mapped.

**Document types — 42 doc-types across 9 groups**: ownership (12 — sale, supply, real estate, barter, gift…), use (4 — lease, leasing, vehicle lease), works (3), services (5 — services, cargo transportation, freight forwarding, storage, insurance), financial (5 — credit, factoring, deposit, guarantee), intermediary (3 — mandate, commission, agency), IP (4 — IP assignment, license, franchise, NDA), partnership (1), special (5 — employment, collective, marriage, alimony, founding). Each is a YAML definition in `playbooks/document_types/`. Currently, the instructions are in Russian, as the pilot projects were carried out using Russian-language documents at pilot companies in Kazakhstan and Armenia. Translating these instructions into any other language is a technical task and will be completed in the near future.

---

## 5. Playbooks, checks, and how the DD Grid is formed

**The check library** is the product's legal substance: **45 global checks** across 15 categories (formal, liability, term, finance, R&W, regulatory, sanctions, confidentiality, IP/IT, change-of-control, HR, disputes, cyber, assignment, others) + **42 doc-type checks** in 9 groups. Global checks apply across document types; doc-type checks apply to specific contract types. The Playbook Studio library exposes **900+ checks** authored by Steloom's domain experts, from which clients compose their playbooks.

**How a playbook is configured — today (hybrid: self-serve composition + guided onboarding).** A playbook is a composition of checks from the library, frozen as a PlaybookVersion (semver, status=published, compiled_checks) and referenced by the run. Clients build their own playbooks via Playbook Studio, selecting from the library of 900+ checks. During onboarding, we also provide hands-on support to help clients align the selected checks with their compliance matrix, and the resulting composition is versioned. This hybrid approach is deliberate — the higher-value question is whether a given playbook composition produces correct, useful results for the client. Playbook Studio enables self-serve iteration from day one, while our team remains available to guide composition during the critical onboarding phase. AI-assisted composition (drafting a playbook from a compliance matrix) is a roadmap item (§3).

**How the applicable playbook is determined.** A deal carries `playbook_version_id` and `model_config_id`; when a run starts, both are frozen into the run. The run's check plan (`RunCheckPlanItem`) is derived from the frozen `compiled_checks`; each (document, check) pair becomes a plan item, executed independently. Two-phase instruction-snapshot freeze (subset at start, extend at checks) makes the run configuration reproducible.

**How the DD Grid is formed.** `DDGridV1ResponseDTO` is built from the run's check results: one cell per (document, check) with `cell_state` ∈ {`defined`, `not_defined`, `not_executed`, `error`}, a verdict, a `review_status`, and a `primary_anchor_id` pointing at the cited fragment (page / clause / span) when one exists. Risk-aware cells (`cell_risk_level`, `top_risk_*`) are computed on top. The drawer shows `display_text`, `execution_status`, the anchor, and QC controls.

**Export:** Excel, Word, JSON; each export lifecycle is audited (`EXPORT_STARTED` / `COMPLETED` / `FAILED`). PDF export is `inline` in the browser; download is not separately audited (R-13, LOW-MEDIUM, documented).

---

## 6. "Not found" — how to read it, what a human checks

A check cell resolves in several ways, and the product is explicit about the difference:

- **`pass`** — the clause / condition was found and satisfied.
- **`fail`** — found and not satisfied.
- **`unclear`** — found, but model confidence or grounding is insufficient to call it. Surfaced for human review.
- **no-verdict / "not found"** — the condition was not located. This is **not** automatically "the clause is absent"; it can mean the clause is phrased differently, extraction missed it, or the check does not apply to this document type.

Observed at E102: 14 `pass` / 0 `fail` / 1 `unclear` / 6 no-verdict (out of 21 checks). The 1 `unclear` and 6 no-verdict are exactly the cells where a human should look. The product never presents "not found" as a legal conclusion — it presents "we did not locate this; a human should decide".

**What a human checks:** every `unclear` and every no-verdict cell; any cell whose anchor is weak or `clause_only` (page/clause located, no exact span quote); the QC step (approve / reject / edit per cell); the final export before downstream use. `review_status` is the canonical human-in-the-loop signal — the DD Grid is a structured draft, not a signed opinion.

Known limitation surfacing here: `_truncated` (partial JSON salvage during extraction) is written by the backend but not yet shown in the UI (R-18, MEDIUM) — a cell built from a truncated extraction can look complete. On the fix list before paying customers (§9).

---

## 7. Deployment — where the product runs, what it takes to launch

**Current deployment: SaaS at `app.steloom.com`.** Single host: Caddy (HTTPS reverse proxy) → FastAPI (uvicorn, 2 workers) → Celery workers (7 queues) → PostgreSQL 16, Redis 7, MinIO (object storage), Ollama (local LLM inference on GPU), and an isolated office-converter microservice (LibreOffice). API and workers run under systemd; infrastructure services in Docker. Deploys via `deploy/deploy-demo.sh` (flock, backup, rsync whitelist, Alembic migrate, frontend build, health checks, `.deploy-meta.json` for traceability). The current demo is deployed at HEAD `e1325f9` (2026-10-26T17:13:48 UTC), matching the audited baseline recorded in the companion Technical Overview.

**Runtime — GPU.** Inference runs on an RTX 5060 Ti 16GB (CUDA 13.2, torch 2.13.0+cu130); Ollama serves `qwen2.5:14b` with 49/49 layers offloaded to GPU. The 15–17 min wall-clock per 18-page / 21-check document is dominated by non-LLM stages (Docling layout, OCR, segmentation, office-converter), not by LLM inference.

**What it takes to launch a SaaS client:** create a tenant, configure the playbook with the client (§5), run onboarding on the client's document set. The pipeline is self-serve after that; the client's legal team works in the web UI.

**On-premise / private cloud.** Architecturally supported (the whole stack is single-host Docker + systemd, and Ollama is local — data never leaves the host), but **not production-hardened as a per-client install today.** Hardening for a private-cloud / on-prem deployment is estimated at roughly 4–8 weeks per client (deployment-level tenant isolation, config management, deployment runbook, backup/restore drills, security review). This is a post-funding direction, driven by enterprise data-residency requirements — mid-market in-house legal is a segment where "our documents stay on our infrastructure" is a real buying criterion. Honest position: SaaS is live; on-prem is architecturally ready but not yet packaged as a product.

**Data handling.** Ollama runs locally — LLM inference is on the host, not a third-party API; client documents do not leave the deployment for inference. PII is tokenized with Fernet encryption; the PII encryption key is set in both dev and demo (R-07 CLOSED; see threat model v1.1 in the Technical Overview, E104/E106). No compliance certification is claimed (no SOC 2, no ISO 27001, no GDPR certification) — see §10.

---

## 8. Team

**Two co-founders:**
- **Founder 1 (business):** business-logic and product ideas; built the initial prototype via vibe-coding. The prototype was rewritten — it is not the production codebase.
- **Founder 2 (CTO):** technical architecture and configuration; rewrote the prototype into the current codebase; sole current engineer on the code.

**Two contract engineers** engaged under specific implementation tasks (correcting code where needed); not full-time, not a standing engineering team. The codebase is currently maintained by the Founders.

**Engineering is 100% in-house** — no outsourced ownership of core components, no in-house fork of a third-party library. Post-funding plan: hire an engineering team (specifics belong in the pitch, not this document).

---

## 9. Known limitations

- **No accuracy benchmark.** E102 / E105 are single synthetic documents — they demonstrate the pipeline works, not that it is accurate across doc types or against ground truth. Accuracy measurement and the evaluation plan are in `Steloom_AI_Quality_and_Limitations.md`. No benchmark is fabricated for this data room.
- **15–17 min wall-clock (measured on GPU)** per 18-page / 21-check document — dominated by non-LLM stages (layout, OCR, segmentation, office-converter), not LLM inference.
- **Base model, no fine-tuning** — `qwen2.5:14b`. Quality comes from prompt engineering + retrieval + conservative fallbacks, not a tuned model.
- **Playbook composition is hybrid** — Playbook Studio is self-serve for check selection; AI-assisted composition and full self-serve onboarding are roadmap (§3, §5).
- **`_truncated` not surfaced in UI** (R-18, MEDIUM) — a cell built from a truncated extraction can look complete. On the fix list before paying customers.
- **No CVE audit / dependency scanning beyond `pip-audit`** in CI.
- **PII tokenizer role map is RU/EN** (R-11, LOW).
- **On-prem / private cloud not production-hardened** — §7.
- **E2E evidence is single-document.** Multi-document orchestration exists and is exercised; cross-document reasoning is not claimed as validated.

---

## 10. What we are not claiming

- Not "production-ready at scale" — the end-to-end evidence is a single synthetic document; the open risk register (**51 risks: 9 CLOSED, 0 HIGH open; open: R-50 MEDIUM, R-51 LOW, R-24 LOW-MEDIUM, R-53 LOW, R-45 LOW**) is documented in `QUALITY_AND_RISKS.md`. R-49 (HIGH, model_configs unauth) was found during live verification and is **CLOSED** as of threat model v1.1 (E106).
- Not "enterprise-grade" — no SOC 2 / ISO 27001 / GDPR certification; data handling is described in §7 and the threat model, not certified.
- Not "AI that replaces lawyers" — the product produces a structured draft with cited anchors and a review status; a human reviews every unclear / no-verdict cell and signs off.
- Not "full 42-doc-type coverage validated" — the library exists (45 global + 42 doc-type checks); which checks a given client runs is configured per playbook, and the end-to-end evidence is a single contract.
- **Pilots are out of scope of this document** — pilot narrative, industries, and geographies are not described here by design.

---

*End of Steloom_Product_Overview. Snapshot `f22e3ba`; HEAD at completion `e1325f9`; demo deployed 2026-10-26T17:13 UTC. Users/buyers = mid-market in-house legal (≥50 docs flow). Formats = 25 extensions from `file_validator.py`. Doc-types = 42 in 9 groups; checks = 45 global + 42 doc-type; Playbook Studio library = 900+ checks. E2E evidence E102 / E105 on GPU (RTX 5060 Ti). Playbook config = hybrid (Studio self-serve + guided onboarding); deployment = SaaS now, on-prem architecturally ready post-funding. 51 risks, 0 HIGH open (R-49 CLOSED). No fabricated benchmark.*