# Steloom / LegalMAS — Threat Model

**Version:** 1.0
**Date:** 2026-10-26
**Snapshot:** audited baseline `f22e3ba`; HEAD at completion `763f2d9`
**Method:** AI-assisted static analysis + targeted runtime verification. Not an independent penetration test.

## Scope

Multi-tenant SaaS processing untrusted legal documents via LLM pipeline. Actor model: external unauthenticated, authenticated user (viewer/editor/admin), compromised editor, malicious document author, local FS attacker.

**Not covered:** nation-state, supply chain (docling/PyMuPDF CVE not audited), side-channel, physical.

## Threat matrix

| # | Threat | Actor | Vector | Mitigation | Gap | Status |
|---|---|---|---|---|---|---|
| T-SSRF-1 | SSRF via document content | Doc author | Inline resource → internal URL | All outbound `httpx.AsyncClient` use `settings.*` URLs (Ollama localhost, OpenAI, MinIO S3 SDK, Prometheus/Loki/Alertmanager localhost). 0 user-controlled URLs in `src/` | None | **Protected** |
| T-XXE-1 | XXE via DOCX XML | Doc author | `<!ENTITY xxe SYSTEM "file:///etc/passwd">` | Main app: 0 XML parsers in `src/`. DOCX → isolated `office-converter` via HTTP | Converter `server.py` XML handling not audited | **Protected (main)** |
| T-CMDI-1 | Shell command injection | Doc author via filename | `; rm -rf /` | 0 `shell=True` in `src/`. OCR uses `subprocess.run([...])` list-args (`document_ocr_language_detection.py:461,667`); input = tmp path from code | None | **Protected** |
| T-RCE-1 | Parser CVE (PDF) | Doc author | Crafted PDF → docling/PyMuPDF CVE | In-process in Celery `heavy_*` worker (not API). PyMuPDF 1.28.2, docling 2.121.0 | `pip-audit` not run; docling stack outdated | **Bounded** (worker isolation) |
| T-OFFICE-1 | Macro/parser RCE via DOCX | Doc author | Crafted DOCX → soffice | Isolated `srv-office-converter` (non-root `appuser`), per-request `profile_dir`, `--headless --nologo --norestore`, 100MB cap, extension whitelist | No `--safe-mode` | **LOW** |
| T-PATH-1 | Path traversal | Auth user | Manipulate `document_id` | MinIO keys use UUIDs from JWT/DB (`artifact_store.py:34`); `PurePosixPath(filename).suffix` MIME only | None | **Protected** |
| T-SQLI-1 | SQL injection | Any | Malicious query | `text()` calls use bind params (`:line_id`) or static defaults; 0 f-string SQL | None | **Protected** |
| T-MAGIC-1 | Malicious file bypass (HEIC/WebP/HEIF) | Doc author | `.heic`/`.webp`/`.heif` с HTML/EXE | Extension whitelist + magic bytes for PDF/ZIP/PNG/JPG/TIFF/BMP/DOC/RTF. **HEIC/WebP/HEIF in EXTENSION_MAP but NOT in MAGIC_BYTES → falls through as `unknown`, not QUARANTINE** (`file_validator.py:200-215`) | Downstream parser is sole defense | **LOW-MEDIUM** (R-24) |
| T-HDR-1 | Content-Disposition injection | Auth user | Upload с `\r\n` в filename → download | `pdf_urls.py:_build_content_disposition` — RFC 5987 safe (strips `\r\n`, URL-encodes). **`documents/exports.py:196 _build_download_headers` — UNSAFE raw f-string** | 3 endpoints (`exports.py:267,332,408`). Starlette 0.41.3 accepts CRLF при init | **MEDIUM** (R-50) |
| T-IDOR-1 | Cross-tenant object access | User tenant B | Tenant A access | `get_scoped_*` + `require_project_role` в 34 endpoint файлах; E101 verified cross-tenant → 404 | None | **Protected** (E101) |
| T-AUTH-1 | Unauthenticated write to model configs | Unauthenticated | POST/PATCH/DELETE `/api/v1/model-configs` без token | `model_configs.py:65,113,171` — POST/PATCH/DELETE без `Depends(get_current_user)`; только `Depends(get_db)`. **Live confirmed:** `GET → 200`, `POST (empty body) → 422` (pydantic validates body before handler, no auth gate) | Full unauth write/delete. Chain: GET (200) → enumerate IDs → DELETE → DoS; PATCH embeddings → pipeline integrity compromise. No `base_url`/`api_key` in schema → no data exfil / no RCE | **HIGH** (R-49) |
| T-AUTH-2 | Public read on document type metadata | Unauthenticated | `GET /api/v1/document-types` без token | `document_types.py:33` — no auth. Returns `{type, name, category, risk_level, language, jurisdiction}` | Metadata public (non-sensitive). Not a data leak per se | **LOW** (R-51) |
| T-JWT-1 | JWT forgery | Any | Algorithm confusion / `none` | `jwt.decode(algorithms=[settings.JWT_ALGORITHM])` explicit; HS256 (`auth_service.py:163`) | None | **Protected** |
| T-XFF-1 | Rate limit bypass via XFF spoofing | External | Spoof `X-Forwarded-For` | Caddy `{remote_host}` overwrites client header; uvicorn `--forwarded-allow-ips=127.0.0.1` | None | **Protected** (E75) |
| T-LLM-COST-1 | LLM cost DoS | Auth user | N parallel runs per deal | `try_start_run` atomically moves single PENDING→RUNNING; **no check for other RUNNING runs of same deal**; **no partial unique index** on `(deal_id, status=running)` | R-33: ~50 LLM calls/run, no per-deal quota | **HIGH** |
| T-PII-1 | PII exfiltration via editor | Compromised editor | Bulk `GET /pii-reveal` | Pre-audit mandatory (`pii_reveal.py:85,119`); **no rate limit** (`rate_limit.py` covers login/logs/admin only) | R-03: no PII reveal rate limit | **MEDIUM-HIGH** |
| T-XSS-1 | XSS → JWT theft | Malicious UI/doc | Stored XSS → `localStorage.mas_dd_api_key` | JWT, role, tenant_id, project_roles все в localStorage (`uiStore.ts:45,51,79-83`) | XSS = full token theft; combined with R-01 (no revocation) — up to 8h window | **MEDIUM** |
| T-PII-KEY-1 | PII plaintext in storage | Ops/deploy | Empty `PII_ENCRYPTION_KEY` | dev: SET (43 chars Fernet base64); demo: SET (43 chars). `pii_encryption.py:97-100` rejects invalid format | None | **Protected** (R-07 CLOSED, E104) |

## Summary

- **Protected:** 9 (T-SSRF, T-XXE-main, T-CMDI, T-PATH, T-SQLI, T-IDOR, T-JWT, T-XFF, T-PII-KEY)
- **Bounded (isolation-limited):** 1 (T-RCE)
- **LOW:** 2 (T-OFFICE, T-AUTH-2)
- **LOW-MEDIUM:** 1 (T-MAGIC)
- **MEDIUM:** 2 (T-HDR, T-XSS)
- **MEDIUM-HIGH:** 1 (T-PII)
- **HIGH:** 2 (T-AUTH-1, T-LLM-COST)
- **Total:** 18 threats

## Not claimed

- No "no vulnerabilities", no "safe", no "production-ready", no compliance claim.
- `pip-audit` not run; docling / PyMuPDF / pdfplumber versions pinned but not CVE-scanned.
- `office-converter/server.py` internal XML / macro handling not audited in depth.
- Threat model covers OWASP-style categories; not a formal STRIDE/PASTA analysis.

---

*End of THREAT_MODEL. 18 threats: 9 Protected, 1 Bounded, 2 LOW, 1 LOW-MEDIUM, 2 MEDIUM, 1 MEDIUM-HIGH, 2 HIGH. See QUALITY_AND_RISKS.md §6 for risk register integration (R-24, R-03, R-33, R-49, R-50, R-51).*
