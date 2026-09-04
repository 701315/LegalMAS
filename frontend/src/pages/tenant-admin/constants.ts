// =============================================================
// src/pages/tenant-admin/constants.ts
//
// Константы для страницы TenantAdmin: CSS утилиты, опции selectов,
// человекочитаемые labels для ролей и статусов.
//
// Дизайн-принцип: держим все magic strings в одном месте, чтобы:
// - легко находить и менять при UI/UX ревизиях
// - переиспользовать в тестах
// - обеспечивать consistency между компонентами
// =============================================================

// ─── CSS Utility Classes ─────────────────────────────────────────────────

/**
 * Стандартный стиль для select/input фильтров в admin panel.
 * Используется в LogsTab (deal_id, level, stage, queue, since, limit).
 */
export const FILTER_CONTROL =
  "min-h-8 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]";

/**
 * Стандартная card-обёртка для секций admin panel.
 * Rounded 2xl + border + shadow-sm.
 */
export const SECTION_CARD =
  "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm";

/**
 * Wrapper для header'а внутри SECTION_CARD.
 * Обеспечивает единый horizontal padding.
 */
export const SECTION_HEADER_WRAP = "px-5";

/**
 * Inner container для header'а — задаёт vertical padding.
 * Разделён с WRAP, потому что divider между header и body должен
 * идти без горизонтального padding (full-width line).
 */
export const SECTION_HEADER_INNER = "py-3";

/**
 * Divider между header и body внутри SECTION_CARD.
 */
export const SECTION_DIVIDER = "border-t border-[var(--border-subtle)]";

/**
 * Стандартный стиль для мелких uppercase labels (10px).
 * Используется для меток полей, заголовков секций, badges.
 */
export const LABEL_XS =
  "text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]";

/**
 * Focus ring для интерактивных элементов.
 * Обеспечивает accessibility (WCAG 2.4.7).
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]";

// ─── Time Range Options ──────────────────────────────────────────────────

/**
 * Опции для селекта "Период" в logs filters.
 * Value — минуты, "0" означает "всё время" (без временного фильтра).
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
 * Отображаемые названия system-level ролей (English canonical fallback).
 * Fallback на raw role code если ключ не найден.
 */
export const ROLE_LABELS: Record<string, string> = {
  superadmin: "Super Administrator",
  tenant_admin: "Administrator",
  member: "Member",
};

/**
 * i18n-ключи для system-level ролей.
 * Использование: t(ROLE_LABEL_KEYS[role]) ?? ROLE_LABELS[role] ?? role
 */
export const ROLE_LABEL_KEYS: Record<string, string> = {
  superadmin: "tenantAdmin:roleLabels.superadmin",
  tenant_admin: "tenantAdmin:roleLabels.tenant_admin",
  member: "tenantAdmin:roleLabels.member",
};

/**
 * Отображаемые названия project-level ролей (English canonical fallback).
 * Используются в UserRow при показе списка проектов пользователя.
 */
export const PROJECT_ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  editor: "Editor",
  viewer: "Viewer",
};

/**
 * i18n-ключи для project-level ролей.
 * Использование: t(PROJECT_ROLE_LABEL_KEYS[role]) ?? PROJECT_ROLE_LABELS[role] ?? role
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
 * Маппинг статуса анализа (run) → отображаемое название + семантический tone.
 * Tone используется для окрашивания текста (см. utils.ts::toneClass).
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


