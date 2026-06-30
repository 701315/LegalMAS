// =============================================================
// src/types/auth.ts
// Типы ролей и пользователя.
// =============================================================

/**
 * Системные роли пользователя в платформе.
 *
 * Канонические:
 * - superadmin   : полный доступ ко всем tenant'ам и данным
 * - tenant_admin : управляет своим tenant'ом и его проектами
 * - member       : видит только назначенные ему проекты
 *
 * Legacy (для dev-совместимости):
 * - admin        : алиас для tenant_admin
 */
export type UserRole =
  | "superadmin"
  | "tenant_admin"
  | "admin"
  | "member"
  | "reviewer"
  | "editor"
  | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  name?: string;
}


