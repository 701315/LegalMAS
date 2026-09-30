// =============================================================
// src/utils/reviewStatus.ts
//
// Single source of truth for mapping a raw `review_status` value
// (from the backend drawer DTO) to a UI bucket.
//
// Two value families coexist by design:
//
//   legacy — risk_detection / clause_presence / pre-v2 records:
//     "ok", "no_issue_detected", "needs_review", "unclear",
//     "not_applicable"
//
//   v2 — field_extraction (see src/engine/checks/result_semantics.py):
//     "clause_defined", "clause_partially_defined", "clause_missing",
//     "unclear"
//
// Any value not listed below is treated as "skip" — the record
// does not count toward pass / fail / unclear aggregates.
// =============================================================

export type ReviewBucket = "pass" | "fail" | "unclear" | "skip";

/**
 * Classify a raw review_status value into a UI bucket.
 *
 * - `null` / `undefined` / empty / whitespace -> "skip".
 * - Unknown non-empty value -> "skip" (fail-safe).
 * - Case-insensitive; surrounding whitespace ignored.
 */
export function classifyReviewStatus(
  status: string | null | undefined,
): ReviewBucket {
  if (typeof status !== "string") return "skip";
  const normalized = status.trim().toLowerCase();
  if (!normalized) return "skip";

  switch (normalized) {
    // Legacy pass family
    case "ok":
    case "no_issue_detected":
    // v2 pass family: clause fully defined
    case "clause_defined":
      return "pass";

    // Legacy fail family
    case "needs_review":
    // v2 fail family: required clause is missing
    case "clause_missing":
      return "fail";

    // Legacy / v2 unclear family
    case "unclear":
    case "clause_partially_defined":
      return "unclear";

    // Explicitly not applicable — do not count.
    case "not_applicable":
      return "skip";

    default:
      return "skip";
  }
}

/**
 * True when the record should not be counted in any aggregate
 * (unknown value, missing value, or explicitly not applicable).
 */
export function isSkippableReviewStatus(
  status: string | null | undefined,
): boolean {
  return classifyReviewStatus(status) === "skip";
}
