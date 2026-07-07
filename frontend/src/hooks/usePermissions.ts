// =============================================================
// src/hooks/usePermissions.ts
// Хук для получения capability-флагов по сделке.
// =============================================================

import { useUIStore } from "../stores/uiStore";

import type { DealPermissions } from "../services/permissions/permissions.types";
import { getDealPermissions } from "../services/permissions/permissions.service";
import type { ProjectRole } from "../api/auth";

/**
 * Возвращает набор прав по конкретной сделке (проекту) на основе
 * глобальной роли пользователя и его роли в проекте.
 */
export function useDealPermissions(dealId: string): DealPermissions {
  const globalRole = useUIStore((s) => s.globalRole);
  const projectRoles = useUIStore((s) => s.projectRoles);

  const projectRole: ProjectRole = projectRoles[dealId] ?? "viewer";

  // globalRole может быть null, если user-info ещё не загружена или
  // пользователь не залогинен. getDealPermissions обрабатывает null
  // как "нет прав" (secure-by-default).
  return getDealPermissions({
    userRole: globalRole,
    projectRole,
  });
}
