// =============================================================
// src/pages/tenant-admin/constants.ts
//
// Constants for the TenantAdmin dashboard: CSS utility classes,
// dropdown options, human-readable labels and keys for roles/statuses.
//
// Design principle: Maintain magic strings centrally to:
// - streamline future UI/UX revisions
// - enable test reusability
// - ensure consistency across components
// =============================================================

// ─── CSS Utility Classes ─────────────────────────────────────────────────

/**
 * Standard styling for select/input filters across the admin panel.
 * Used in LogsTab (deal_id, level, stage, queue, since, limit).
 */
export const FILTER_CONTROL =
  "min-h-8 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]";

/**
 * Standard card wrapper for admin panel sections.
 * Rounded 2xl + border + shadow-sm.
 */
export const SECTION_CARD =
  "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm";

/**
 * Header wrapper inside SECTION_CARD.
 * Enforces unified horizontal padding.
 */
export const SECTION_HEADER_WRAP = "px-5";

/**
 * Inner container for section headers — applies vertical padding.
 * Separated from WRAP so dividers can span full width.
 */
export const SECTION_HEADER_INNER = "py-3";

/**
 * Full-width divider between header and body inside SECTION_CARD.
 */
export const SECTION_DIVIDER = "border-t border-[var(--border-subtle)]";

/**
 * Standard style for small uppercase labels (10px).
 * Used for field labels, section headers, and badges.
 */
export const LABEL_XS =
  "text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]";

/**
 * Focus ring for interactive elements ensuring WCAG 2.4.7 accessibility compliance.
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]";

// ─── Time Range Options ──────────────────────────────────────────────────

/**
 * Time range period options for logs filtering.
 * Value in minutes, "0" represents "all time" (no temporal filter).
 */
export const SINCE_OPTIONS: { value: string; label: string; labelKey: string }[] = [
  { value: "15", label: "15 min", labelKey: "tenantAdmin:filters.since.15min" },
  { value: "60", label: "1 hour", labelKey: "tenantAdmin:filters.since.1h" },
  { value: "240", label: "4 hours", labelKey: "tenantAdmin:filters.since.4h" },
  { value: "1440", label: "24 hours", labelKey: "tenantAdmin:filters.since.24h" },
  { value: "2880", label: "48 hours", labelKey: "tenantAdmin:filters.since.48h" },
  { value: "10080", label: "7 days", labelKey: "tenantAdmin:filters.since.7d" },
  { value: "43200", label: "30 days", labelKey: "tenantAdmin:filters.since.30d" },
  { value: "0", label: "All time", labelKey: "tenantAdmin:filters.since.allTime" },
];

// ─── Role Labels (human-readable) ────────────────────────────────────────

/**
 * System-level roles (English canonical fallback).
 */
export const ROLE_LABELS: Record<string, string> = {
  superadmin: "Super Administrator",
  tenant_admin: "Administrator",
  member: "Member",
};

/**
 * i18n keys for system-level roles.
 */
export const ROLE_LABEL_KEYS: Record<string, string> = {
  superadmin: "tenantAdmin:roleLabels.superadmin",
  tenant_admin: "tenantAdmin:roleLabels.tenant_admin",
  member: "tenantAdmin:roleLabels.member",
};

/**
 * Project-level roles (English canonical fallback).
 */
export const PROJECT_ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  editor: "Editor",
  viewer: "Viewer",
};

/**
 * i18n keys for project-level roles.
 */
export const PROJECT_ROLE_LABEL_KEYS: Record<string, string> = {
  admin: "tenantAdmin:roleLabels.projectAdmin",
  editor: "tenantAdmin:roleLabels.projectEditor",
  viewer: "tenantAdmin:roleLabels.projectViewer",
};

// ─── Run Status Configuration ────────────────────────────────────────────

export interface RunStatusDescriptor {
  label: string;
  labelKey: string;
  tone: "ok" | "warn" | "error" | "neutral";
}

/**
 * Run status descriptor mapping.
 */
export const RUN_STATUS_CONFIG: Record<string, RunStatusDescriptor> = {
  completed: {
    label: "Completed",
    labelKey: "tenantAdmin:runStatusLabels.completed",
    tone: "ok",
  },
  completed_with_errors: {
    label: "With errors",
    labelKey: "tenantAdmin:runStatusLabels.completed_with_errors",
    tone: "warn",
  },
  failed: {
    label: "Failed",
    labelKey: "tenantAdmin:runStatusLabels.failed",
    tone: "error",
  },
  running: {
    label: "Running",
    labelKey: "tenantAdmin:runStatusLabels.running",
    tone: "neutral",
  },
  pending: {
    label: "Queued",
    labelKey: "tenantAdmin:runStatusLabels.pending",
    tone: "neutral",
  },
};


