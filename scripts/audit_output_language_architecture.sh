#!/usr/bin/env bash
# Read-only audit for Steloom: UI i18n vs. analysis/output-language architecture.
# Usage:
#   chmod +x audit_output_language_architecture.sh
#   ./audit_output_language_architecture.sh
#   ./audit_output_language_architecture.sh > output_language_audit.txt

set -uo pipefail

BACKEND="${BACKEND:-/srv/steloom-dev/src}"
FRONTEND="${FRONTEND:-/srv/steloom-dev/frontend}"
MAX_MATCHES="${MAX_MATCHES:-80}"

have() { command -v "$1" >/dev/null 2>&1; }

if have rg; then
  SEARCH=(rg -n -i --hidden --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/.next/**' --glob '!**/dist/**' --glob '!**/build/**' --glob '!**/.venv/**' --glob '!**/venv/**' --glob '!**/__pycache__/**')
else
  SEARCH=(grep -RInE --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist --exclude-dir=build --exclude-dir=.venv --exclude-dir=venv --exclude-dir=__pycache__)
fi

section() {
  printf '\n\n================================================================================\n'
  printf '%s\n' "$1"
  printf '================================================================================\n'
}

note() { printf '\n>>> %s\n' "$1"; }

search() {
  local root="$1"
  local pattern="$2"
  local label="$3"

  note "$label"
  if [[ ! -d "$root" ]]; then
    printf 'SKIPPED: directory not found: %s\n' "$root"
    return 0
  fi

  local result
  result=$("${SEARCH[@]}" "$pattern" "$root" 2>/dev/null | head -n "$MAX_MATCHES" || true)
  if [[ -n "$result" ]]; then
    printf '%s\n' "$result"
  else
    printf 'No matches found.\n'
  fi
}

files() {
  local root="$1"
  local label="$2"
  shift 2
  note "$label"
  if [[ ! -d "$root" ]]; then
    printf 'SKIPPED: directory not found: %s\n' "$root"
    return 0
  fi
  find "$root" -type f \( "$@" \) \
    -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.next/*' \
    -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/.venv/*' \
    | sort | head -n "$MAX_MATCHES" || true
}

printf 'Steloom output-language architecture audit\n'
printf 'Generated: %s\n' "$(date -Is)"
printf 'Backend:  %s\n' "$BACKEND"
printf 'Frontend: %s\n' "$FRONTEND"
printf 'This script is read-only. It does not modify repository files or databases.\n'
printf 'Tip: install ripgrep (rg) for faster and more complete output.\n'

section '0. Repository presence and likely technology files'
for path in "$BACKEND" "$FRONTEND"; do
  if [[ -d "$path" ]]; then
    printf 'OK: %s\n' "$path"
  else
    printf 'MISSING: %s\n' "$path"
  fi
done
files "$BACKEND" 'Backend manifests and settings' -name 'pyproject.toml' -o -name 'requirements*.txt' -o -name 'alembic.ini' -o -name '.env*' -o -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml'
files "$FRONTEND" 'Frontend manifests and i18n configuration candidates' -name 'package.json' -o -name 'next.config.*' -o -name 'vite.config.*' -o -name 'i18n.*' -o -name 'middleware.*' -o -name 'messages.*' -o -name '*.json'

section '1. Frontend: existing interface i18n'
search "$FRONTEND" 'next-intl|react-i18next|i18next|react-intl|IntlProvider|useTranslation|useTranslations|createI18n|locales|supportedLocales|defaultLocale|locale' 'i18n library, locale config, and translation hooks'
search "$FRONTEND" 'language|locale|outputLocale|output_language|analysisLanguage|analysis_language|documentLanguage|document_language|jurisdiction' 'Language-related UI state, API fields, and labels'
search "$FRONTEND" 'localStorage|cookie|setCookie|router\.push|router\.replace|useRouter|params\.locale|\[locale\]' 'Where the UI language preference is persisted or routed'
search "$FRONTEND" 'fetch\(|axios|/api/|apiClient|ky\(' 'API client calls: inspect whether locale headers or output_locale are sent'

section '2. Backend: API contracts, persistence, and workers'
search "$BACKEND" 'FastAPI|APIRouter|@router\.(get|post|put|patch)|BaseModel|pydantic|SQLAlchemy|Mapped\[|Column\(' 'Routes, request/response schemas, and persistence models'
search "$BACKEND" 'locale|language|output_locale|outputLanguage|analysis_language|analysisLanguage|document_language|documentLanguage|ui_locale|uiLocale|jurisdiction' 'Existing language fields in backend code'
search "$BACKEND" 'Celery|@shared_task|@app\.task|delay\(|apply_async|BackgroundTasks|worker' 'Asynchronous analysis/localization jobs'
search "$BACKEND" 'OpenAI|Anthropic|ollama|chat\.completions|responses\.create|structured.?output|json_schema|response_format' 'LLM calls and structured-output configuration'
search "$BACKEND" 'finding|findings|risk|risks|analysis_run|analysisrun|instruction_version|instructionversion|evidence|citation|quote|chunk' 'Core entities for matrix cells, risk definitions, evidence, and instruction versions'

section '3. Database migrations and canonical result shape'
search "$BACKEND" 'CREATE TABLE|op\.create_table|add_column|ALTER TABLE|JSONB|JSON|finding_localization|localization|translation' 'Migrations: check whether findings and localized text are modelled separately'
search "$BACKEND" 'summary|recommendation|description|explanation|severity|confidence|status|risk_key|risk_id|source_ref|page_from|page_to|char_start|char_end' 'Finding fields: distinguish structured facts from display text'

section '4. High-risk coupling patterns to review'
search "$BACKEND" 'language.*=.*request|request.*language|locale.*=.*request|request.*locale' 'Potential coupling: request/UI locale passed directly into analysis logic'
search "$BACKEND" 'translate.*analysis|analysis.*translate|translate.*finding|finding.*translate|localiz' 'Translation/localization implementations or placeholders'
search "$FRONTEND" 'severity.*[А-Яа-я]|high.*[А-Яа-я]|risk.*[А-Яа-я]|summary.*[А-Яа-я]|recommendation.*[А-Яа-я]' 'Possible hard-coded Russian result labels in frontend source'
search "$BACKEND" 'severity.*[А-Яа-я]|risk.*[А-Яа-я]|summary.*[А-Яа-я]|recommendation.*[А-Яа-я]' 'Possible hard-coded Russian result labels in backend or prompts'
search "$BACKEND" 'markdown|html|render.*table|table.*render|csv|xlsx|export' 'Exports: verify selected output locale is propagated independently'

section '5. Prompts and instruction assets'
files "$BACKEND" 'Candidate prompt/instruction files' -iname '*prompt*' -o -iname '*instruction*' -o -iname '*risk*' -o -iname '*template*' -o -iname '*.md' -o -iname '*.yaml' -o -iname '*.yml'
search "$BACKEND" 'output language|response language|язык ответа|язык анализа|JSON Schema|risk_key|source_refs|evidence' 'Whether prompts define analysis language, output language, and structured evidence explicitly'

section '6. Suggested target contract'
cat <<'EOF'

Audit the code against this separation. These fields should not be aliases:

  ui_locale          User interface language, e.g. en-US / ru-RU.
  output_locale      Language of displayed finding text; selected by the viewer.
  analysis_language  Language used by the legal-check prompt/instruction.
  document_language  Detected or confirmed property of a document/section.
  jurisdiction       Legal context; never infer it from a language.

Recommended minimal entities:

  risk_definitions
    id, instruction_version_id, risk_key, severity_policy, ...

  findings
    id, document_version_id, instruction_version_id, risk_key,
    status, severity, confidence,
    canonical_language, canonical_summary, canonical_recommendation,
    finding_version, created_at

  finding_evidence
    id, finding_id, section_id, page_from, page_to,
    quote_original, char_start, char_end

  finding_localizations
    id, finding_id, locale, title, summary, recommendation,
    source_finding_version, glossary_version, prompt_version,
    quality_status, created_at

A matrix API should return stable codes and requested localized display text:

  GET /analysis-runs/{run_id}/matrix?output_locale=en-US

  {
    "run_id": "...",
    "output_locale": "en-US",
    "rows": [{"document_id": "...", "document_name": "..."}],
    "columns": [{"risk_key": "unilateral_price_change", "title": "Unilateral price change"}],
    "cells": [{
      "document_id": "...",
      "risk_key": "unilateral_price_change",
      "status": "present",
      "severity": "high",
      "summary": "The supplier may change the price unilaterally.",
      "content_locale": "en-US",
      "canonical_locale": "ru-RU",
      "localization_status": "ready",
      "finding_id": "..."
    }]
  }

Expected behavior when a user changes output_locale:
  1. Do NOT rerun OCR, parsing, retrieval, or legal analysis.
  2. Read finding_localizations for (finding_id, output_locale, finding_version).
  3. If absent, return canonical text with content_locale set accordingly,
     enqueue a localization job, and update the cell when ready.
  4. Keep original evidence immutable; show translated quotes as translations,
     never as the source document text.
EOF

section '7. Manual scoring checklist'
cat <<'EOF'

Score each item: 0 = absent, 1 = partial, 2 = implemented and tested.

[ ] UI locale is stored independently from analysis/output locale.
[ ] Request schemas expose output_locale separately from analysis_language.
[ ] The database stores document language independently from jurisdiction.
[ ] Risk columns use stable risk_key / risk_definition IDs, not LLM-generated titles.
[ ] A finding stores structured status, severity, confidence, and evidence separately.
[ ] Findings have immutable source references to document version, page, section, offsets.
[ ] Localized texts are in a separate finding_localizations entity/table.
[ ] Localization is keyed by finding version + target locale and is cacheable.
[ ] Changing output language never creates a new legal-analysis run.
[ ] The system visibly marks fallback/canonical text while localization is pending.
[ ] Original quotation and translated quotation are separate values in the UI/API.
[ ] Prompt/instruction/model/glossary versions are recorded for auditability.
[ ] Exports receive output_locale but preserve original evidence and metadata.
[ ] Tests cover RU document + RU analysis + EN output; EN document + EN analysis + RU output;
    missing translation fallback; and instruction-version changes.

Interpretation:
  24-28: strong foundation for multilingual audited results.
  16-23: workable, but close the gaps before scaling languages/organizations.
   0-15: first introduce a canonical finding model before adding more UI localization.
EOF

section '8. Focused commands after the audit'
cat <<'EOF'

# Save an audit report:
./audit_output_language_architecture.sh | tee output_language_audit.txt

# Find exact API routes around results/matrix:
rg -n -i 'analysis-runs|findings|matrix|results' /srv/steloom-dev/src

# Find frontend screens displaying findings/results:
rg -n -i 'finding|risk|matrix|analysis result|results' /srv/steloom-dev/frontend

# Search hard-coded Russian strings, excluding dependencies:
rg -n --hidden '[А-Яа-яЁё]' /srv/steloom-dev/frontend \
  -g '!node_modules/**' -g '!*.lock' -g '!*.map'
EOF

printf '\nAudit completed. Review sections 1-5 and score section 7 before changing schemas.\n'


