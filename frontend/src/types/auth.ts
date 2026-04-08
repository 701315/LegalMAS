// =============================================================
// src/types/auth.ts
// Типы ролей и пользователя.
// =============================================================

/**
 * Роли пользователей в системе.
 * Уровни: viewer=1, editor=2, reviewer=3, admin=4
 */
export type UserRole = "superadmin" | "admin" | "reviewer" | "editor" | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  name?: string;
}

