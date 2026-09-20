# ADR-0001: Multilingual Result Presentations

- Status: Accepted
- Date: 2026-09-06
- Decision owners: Product Engineering
- Scope: Run-scoped review results, DD Grid, DD Matrix, document review,
  DD requests, risk summaries, and exports

## Context

Steloom supports several independent language concepts:

1. `User.ui_locale`
   The user's interface language, for example `en` or `ru`.

2. `Deal.primary_language`
   The primary business language of the deal.

3. `DocumentVersion.detected_languages`
   The authoritative detected-language inventory for a document version.

4. `DocumentRunLanguageResolution`
   The run-scoped decision about the requested and effective language used
   for a concrete document version. It records `requested_language`,
   `effective_language`, `resolution_status`, `reason_code`, and
   language-specific artifact references.

5. `CheckResult`
   The canonical result of one check for one document or document segment
   within one run. It owns factual result state, severity, evidence,
   provenance, execution state, QC state, canonical display semantics,
   and review workflow state.

A user must be able to work in a chosen language without translating every
DD Grid cell manually. At the same time, the system must preserve the original
document text, evidence, provenance, review traceability, and result identity.

The existing `CheckResult` uniqueness model is:

- `(run_id, document_id, check_id)` for non-segment results.
- `(run_id, document_id, segment_id, check_id)` for segment results.

The active production check execution path persists results through
`ResultRepository.upsert_single_check_result(...)`. It must remain idempotent
and must not create duplicate canonical results for multiple presentation
languages.

## Decision

Steloom adopts the following multilingual result architecture.

### 1. One canonical result per check identity

`CheckResult` remains the single canonical record for a check execution.

It owns:

- result and severity;
- execution status and error details;
- evidence references;
- page, clause, element, bounding-box, segment, chunk, and context trace;
- structured data;
- check metadata;
- QC state and reviewer information;
- canonical workflow semantics;
- canonical source/effective execution-language metadata when available.

A canonical `CheckResult` is never duplicated solely because the same finding
is displayed in another language.

### 2. Presentation is a separate child layer

Locale-specific user-facing content is stored separately from the canonical
result.

The future persistence entity is named `CheckResultPresentation`.

Its logical identity is:

```text
(check_result_id, locale, content_version)
```

A presentation record contains locale-specific content such as:

- translated display text;
- translated review message;
- translated DD request text or localized request fragments;
- localized check name where this is not supplied by a stable playbook
  translation dictionary;
- translation state and provenance;
- source content fingerprint;
- approval/review metadata where required.

The canonical result remains authoritative if no presentation exists.

### 3. Result language is selected once per review session

A review page has one explicit `presentation_locale`.

The initial locale resolution order is:

1. Explicit page-level locale selected by the user.
2. Persisted `User.ui_locale`.
3. `Deal.primary_language`.
4. Platform default locale.

The selected presentation locale applies to:

- DD Grid;
- DD Matrix;
- document result cards;
- check result display text;
- review messages;
- DD requests;
- risk summaries;
- generated export headings and explanatory text.

The selection is not per cell.

### 4. Original evidence is always available

The original source text is never silently replaced.

For every translated result, the UI must provide access to:

- original evidence text;
- document/page/clause/segment reference;
- source language;
- presentation locale;
- translation status;
- translation provenance where available.

The original document language and a translated presentation language are
different concepts.

### 5. Missing translations use explicit fallback

A missing presentation must not cause empty review cells and must not silently
appear as a translated result.

The fallback behavior is:

1. Show a completed locale-specific presentation when available.
2. Otherwise show canonical/source-language content.
3. Show a visible state that the requested presentation is pending,
   processing, unavailable, or failed.
4. Automatically refresh the affected result set when batch generation
   completes.

The ordinary review flow never requires a user to press "Translate" on every
cell.

### 6. Translation preparation is run-scoped and batched

Translation generation is requested for a whole run and locale, not one
browser request per DD Grid cell.

A batch may be triggered by:

- run completion for the deal primary language;
- first selection of an unavailable presentation locale;
- explicit preparation of an export locale;
- an administrative or review workflow action.

Batch processing must:

- deduplicate identical source content;
- process high and critical findings before lower-priority content;
- preserve partial progress;
- support retryable and permanent failures;
- avoid blocking review access;
- preserve the canonical result and original evidence;
- reuse completed approved presentations where source content fingerprints
  still match.

### 7. Translation lifecycle is explicit

A presentation has a lifecycle distinct from `CheckResult.execution_status`.

Initial supported states are:

```text
pending
processing
ready
failed
reviewed
approved
stale
```

Interpretation:

- `pending`: presentation requested but not yet started.
- `processing`: translation job is active.
- `ready`: generated and available for normal review.
- `failed`: generation did not complete; canonical fallback remains visible.
- `reviewed`: a human reviewed the presentation.
- `approved`: approved for controlled or formal output.
- `stale`: source content changed after the presentation was created.

### 8. Exports use an explicit locale

Exports must accept an explicit `presentation_locale`.

An export may use:

- ready presentation content for the selected locale;
- canonical/original fallback content where presentation is unavailable;
- a visible report-level translation-status disclosure if fallback occurred.

The source document, evidence coordinates, canonical result state, and QC data
remain unchanged by export localization.

## Consequences

### Positive consequences

- Users choose a language once and receive the complete review experience
  in that language.
- DD Grid interaction does not require hundreds of per-cell translation actions.
- Legal and factual traceability remains intact because canonical evidence and
  provenance are preserved.
- QC state remains attached to one canonical finding.
- Run finalization, risk aggregation, and idempotent result persistence do not
  double-count multilingual presentations.
- Translation work can be cached, deduplicated, retried, reviewed, and approved.

### Costs and constraints

- A presentation batch requires asynchronous orchestration and progress tracking.
- API responses need explicit locale and fallback metadata.
- The UI must render pending and fallback states clearly.
- Presentation freshness must be checked against a source content fingerprint.
- Translation usage must be observable and auditable.
- A locale-specific presentation must not overwrite canonical evidence or
  canonical factual result fields.

## Non-goals

This decision does not:

- translate the original contract in place;
- create a separate `CheckResult` for each language;
- modify `CheckResult` uniqueness constraints to include a locale;
- use `User.ui_locale` as the document execution language;
- replace source evidence with translated evidence;
- require a translation provider implementation in the first schema commit;
- change the legacy `CheckResultRepository` compatibility seam.

## Implementation sequence

1. Add the `CheckResultPresentation` persistence model and migration.
2. Add repository methods for idempotent presentation retrieval and upsert.
3. Add run-scoped batch request and progress data.
4. Extend review API responses with presentation locale and fallback metadata.
5. Add frontend locale selector and automatic background refresh.
6. Add translation provider integration and batch worker.
7. Add reviewed/approved translation workflow.
8. Add export locale selection and fallback disclosure.
9. Address `CheckResultRepository` legacy compatibility separately.

## Compatibility rules

- Existing runs without language resolution remain readable.
- Existing `CheckResult.display_text` remains canonical fallback content.
- Existing review endpoints remain compatible until locale-aware response fields
  are additive and clients are migrated.
- Existing QC mutations continue to address canonical finding identity:
  run, document, segment, and check.
- Existing `ResultRepository.upsert_single_check_result(...)` remains the
  production owner of canonical result persistence.
