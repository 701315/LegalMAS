// =============================================================
// src/pages/tenant-admin/types.ts
//
// Общие типы для страницы TenantAdmin и её подкомпонентов.
//
// Дизайн-принцип: типы этой страницы держим отдельно от глобальных
// types.ts, потому что это внутренняя терминология admin panel,
// не бизнес-модели проекта.
// =============================================================

/**
 * Основные табы в главной панели администратора.
 * Порядок соответствует UI: projects → users → monitoring → logs → alerts
 */
export type AdminTab = "projects" | "users" | "monitoring" | "logs" | "alerts";

/**
 * Sub-табы внутри ProjectDrillDown (детальный вид проекта).
 * Показывается после клика на проект в списке.
 */
export type ProjectDrillTab = "overview" | "members" | "logs";

/**
 * Фильтр для секции "Проблемы и ошибки" в ProjectDrillDown.
 * - all: все типы ошибок
 * - document: только ошибки на уровне документов
 * - run: только ошибки на уровне runs (анализов)
 */
export type ErrorFilter = "all" | "document" | "run";


