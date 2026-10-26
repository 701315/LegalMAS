cat > docs/technical-dd/internal/THREAT_MODEL.md <<'ENDOFFILE_TM'
# Steloom / LegalMAS — Threat Model

**Version:** 1.1
**Date:** 2026-10-26
**Snapshot:** audited baseline `f22e3ba`; HEAD at completion `e1325f9`
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
| T-AUTH-1 | Unauthenticated write to model configs | Unauthenticated | POST/PATCH/DELETE `/api/v1/model-configs` без token | `require_superadmin()` Depends guard (`security.py`); POST/PATCH/DELETE → `Depends(require_superadmin)`; GET/usage → `Depends(get_current_user)`; frontend hides write buttons for non-superadmin + banner. 15/15 tests. | Was: full unauth write/delete. Now: 401 no-token, 403 member, 403 tenant_admin, 422 superadmin empty-body. | **CLOSED** (R-49, E106) |
| T-AUTH-2 | Public read on document type metadata | Unauthenticated | `GET /api/v1/document-types` без token | `document_types.py:33` — no auth. Returns `{type, name, category, risk_level, language, jurisdiction}` | Metadata public (non-sensitive). Not a data leak per se | **LOW** (R-51) |
| T-JWT-1 | JWT forgery | Any | Algorithm confusion / `none` | `jwt.decode(algorithms=[settings.JWT_ALGORITHM])` explicit; HS256 (`auth_service.py:163`) | None | **Protected** |
| T-XFF-1 | Rate limit bypass via XFF spoofing | External | Spoof `X-Forwarded-For` | Caddy `{remote_host}` overwrites client header; uvicorn `--forwarded-allow-ips=127.0.0.1` | None | **Protected** (E75) |
| T-LLM-COST-1 | LLM cost DoS | Auth user | N parallel runs per deal (both `/deals/{id}/run` and `/playbook/rebuild-and-rerun`) | Partial unique index `uq_runs_one_active_per_deal WHERE status IN ('pending','running')` (`bf78307e1293`); API `IntegrityError` → 409 + `X-Active-Run-Id`; MissingGreenlet fix (cached ORM FK before rollback). Both endpoints covered (R-33 + R-52). | Was: N parallel runs allowed → cost amplification. Now: 2nd concurrent → 409 with pointer to active run. | **CLOSED** (R-33 + R-52, E106) |
| T-PII-1 | PII exfiltration via editor | Compromised editor | Bulk `GET /pii-reveal` | Pre-audit mandatory + `check_pii_reveal_rate_limit` 10/min per user (scope=`pii_reveal`, identity=`user.id` not IP; Caddy-safe). 8/8 tests. | Was: no rate limit → bulk exfil amplifier. Now: 11th rapid call → 429 + `Retry-After: 60`. | **CLOSED** (R-03, E106) |
| T-XSS-1 | XSS → JWT theft | Malicious UI/doc | Stored XSS → `localStorage.mas_dd_api_key` | JWT, role, tenant_id, project_roles все в localStorage (`uiStore.ts:45,51,79-83`) | XSS = full token theft; combined with R-01 (no revocation) — up to 8h window | **MEDIUM** |
| T-PII-KEY-1 | PII plaintext in storage | Ops/deploy | Empty `PII_ENCRYPTION_KEY` | dev: SET (43 chars Fernet base64); demo: SET (43 chars). `pii_encryption.py:97-100` rejects invalid format | None | **Protected** (R-07 CLOSED, E104) |

## Summary

- **Protected:** 9 (T-SSRF, T-XXE-main, T-CMDI, T-PATH, T-SQLI, T-IDOR, T-JWT, T-XFF, T-PII-KEY)
- **Bounded (isolation-limited):** 1 (T-RCE)
- **CLOSED (was MEDIUM-HIGH/HIGH):** 3 (T-PII, T-AUTH-1, T-LLM-COST — all fixed 2026-10-26, E106)
- **LOW:** 2 (T-OFFICE, T-AUTH-2)
- **LOW-MEDIUM:** 1 (T-MAGIC)
- **MEDIUM:** 2 (T-HDR, T-XSS)
- **Total:** 18 threats (0 MEDIUM-HIGH open, 0 HIGH open)

## Not claimed

- No "no vulnerabilities", no "safe", no "production-ready", no compliance claim.
- `pip-audit` not run; docling / PyMuPDF / pdfplumber versions pinned but not CVE-scanned.
- `office-converter/server.py` internal XML / macro handling not audited in depth.
- Threat model covers OWASP-style categories; not a formal STRIDE/PASTA analysis.

---

*End of THREAT_MODEL. 18 threats: 9 Protected, 1 Bounded, 3 CLOSED (T-PII, T-AUTH-1, T-LLM-COST — verified 2026-10-26, E106), 2 LOW, 1 LOW-MEDIUM, 2 MEDIUM. 0 MEDIUM-HIGH open, 0 HIGH open. See QUALITY_AND_RISKS.md §6 for risk register integration (R-03, R-24, R-33, R-49, R-50, R-51, R-52, R-53).*
ENDOFFILE_TM