// =============================================================
// src/hooks/usePermissions.ts
// Hook for retrieving capability flags for a specific deal.
// =============================================================

import { useUIStore } from "../stores/uiStore";

import type { DealPermissions } from "../services/permissions/permissions.types";
import { getDealPermissions } from "../services/permissions/permissions.service";
import type { ProjectRole } from "../api/auth";

/**
 * Returns the set of permissions for a specific deal (project) based on
 * the user's global role and their assigned project role.
 */
export function useDealPermissions(dealId: string): DealPermissions {
  const globalRole = useUIStore((s) => s.globalRole);
  const projectRoles = useUIStore((s) => s.projectRoles);

  const projectRole: ProjectRole = projectRoles[dealId] ?? "viewer";

  // globalRole can be null if user-info is not yet loaded or
  // the user is not authenticated. getDealPermissions treats null
  // as "no permissions" (secure-by-default).
  return getDealPermissions({
    userRole: globalRole,
    projectRole,
  });
}

