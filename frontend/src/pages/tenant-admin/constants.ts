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
export const SINCE_OPTIONS: { value: string; label: string }[] = [
  { value: "15", label: "15 мин" },
  { value: "60", label: "1 час" },
  { value: "240", label: "4 часа" },
  { value: "1440", label: "24 часа" },
  { value: "2880", label: "48 часов" },
  { value: "10080", label: "7 дней" },
  { value: "43200", label: "30 дней" },
  { value: "0", label: "Всё время" },
];

// ─── Role Labels (human-readable) ────────────────────────────────────────

/**
 * Отображаемые названия system-level ролей.
 * Fallback на raw role code если ключ не найден.
 */
export const ROLE_LABELS: Record<string, string> = {
  superadmin: "Супер-администратор",
  tenant_admin: "Администратор",
  member: "Участник",
};

/**
 * Отображаемые названия project-level ролей.
 * Используются в UserRow при показе списка проектов пользователя.
 */
export const PROJECT_ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  editor: "Редактор",
  viewer: "Наблюдатель",
};

// ─── Run Status Configuration ────────────────────────────────────────────

/**
 * Маппинг статуса анализа (run) → отображаемое название + семантический tone.
 * Tone используется для окрашивания текста (см. utils.ts::toneClass).
 */
export const RUN_STATUS_CONFIG: Record<
  string,
  { label: string; tone: "ok" | "warn" | "error" | "neutral" }
> = {
  completed: { label: "Завершён", tone: "ok" },
  completed_with_errors: { label: "С ошибками", tone: "warn" },
  failed: { label: "Ошибка", tone: "error" },
  running: { label: "Выполняется", tone: "neutral" },
  pending: { label: "В очереди", tone: "neutral" },
};


