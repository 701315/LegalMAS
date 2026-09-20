// =============================================================
// src/pages/tenant-admin/types.ts
//
// Shared types for TenantAdmin page and its sub-components.
//
// Design principle: Types for this page are kept separate from
// global types.ts because this is internal admin panel terminology,
// not the project's business domain models.
// =============================================================

/**
 * Main tabs in the admin dashboard.
 * Order corresponds to UI: projects → users → monitoring → logs → alerts
 */
export type AdminTab = "projects" | "users" | "monitoring" | "logs" | "alerts" | "localePolicy";

/**
 * Sub-tabs inside ProjectDrillDown (project detail view).
 * Displayed after clicking a project in the list.
 */
export type ProjectDrillTab = "overview" | "members" | "logs";

/**
 * Filter for the "Problems and errors" section in ProjectDrillDown.
 * - all: all error types
 * - document: document-level errors only
 * - run: run-level (analysis) errors only
 */
export type ErrorFilter = "all" | "document" | "run";


