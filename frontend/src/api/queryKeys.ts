// =============================================================
// src/api/queryKeys.ts
// =============================================================

/**
 * Централизованные ключи React Query.
 *
 * Идея в том, что одинаковые серверные данные должны иметь
 * одинаковый query key во всех компонентах приложения.
 *
 * Если Dashboard и AppShell используют один и тот же ключ,
 * то после invalidateQueries оба интерфейса синхронно получат
 * обновлённые данные.
 */
export const queryKeys = {
  userProjects: (userId: string) => ["user-projects", userId] as const,
  adminTenants: ["admin", "tenants"] as const,
  adminTenant: (tenantId: string) => ["admin", "tenants", tenantId] as const,
};


