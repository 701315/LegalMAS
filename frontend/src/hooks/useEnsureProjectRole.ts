// =============================================================
// src/hooks/useEnsureProjectRole.ts
// При маунте загружает роль текущего пользователя в проекте
// и записывает её в uiStore, если она ещё не известна.
// =============================================================

import React from "react";
import { useUIStore } from "../stores/uiStore";
import { projectMembersApi } from "../api/projectMembers";

export function useEnsureProjectRole(dealId: string): void {
  const userId = useUIStore((s) => s.userId);
  const globalRole = useUIStore((s) => s.globalRole);
  const projectRoles = useUIStore((s) => s.projectRoles);
  const setProjectRole = useUIStore((s) => s.setProjectRole);

  const isTenantScopedAdmin =
    globalRole === "superadmin" || globalRole === "tenant_admin";
  const alreadyResolved = dealId in projectRoles;

  React.useEffect(() => {
    // superadmin и tenant_admin не нуждаются в membership-lookup
    if (isTenantScopedAdmin) return;
    if (alreadyResolved) return;
    if (!dealId || !userId) return;

    let cancelled = false;

    projectMembersApi
      .list(dealId)
      .then((members) => {
        if (cancelled) return;
        const me = members.find((m) => m.user_id === userId);
        setProjectRole(dealId, me?.role ?? "viewer");
      })
      .catch(() => {
        if (cancelled) return;
        setProjectRole(dealId, "viewer");
      });

    return () => {
      cancelled = true;
    };
  }, [dealId, userId, isTenantScopedAdmin, alreadyResolved, setProjectRole]);
}

