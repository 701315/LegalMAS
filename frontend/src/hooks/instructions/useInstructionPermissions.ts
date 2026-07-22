// src/hooks/instructions/useInstructionPermissions.ts
// RBAC для instruction management.
// Расширяет существующую модель globalRole + projectRoles.

import { useAuth } from "../useAuth";

export interface InstructionPermissions {
  // Global base (playbooks, doc-types) — только superadmin
  canViewGlobalBase: boolean;
  canEditGlobalBase: boolean;
  canPublishGlobalBase: boolean;

  // Tenant overrides
  canViewTenantOverrides: boolean;
  canEditTenantOverride: boolean;
  canActivateTenantOverride: boolean;

  // Deal overrides (проверяется отдельно через dealPermissions)
  canViewDealOverrides: boolean;
  canEditDealOverride: boolean;
  canActivateDealOverride: boolean;

  // История версий
  canViewVersionHistory: boolean;
}

/**
 * Вычисляет permission набор для instruction management.
 *
 * @param dealCapabilities — capabilities из useDealPermissions(dealId),
 *   передавать только для deal-level контекста.
 */
export function useInstructionPermissions(
  dealCapabilities?: {
    canManageRequests?: boolean;
  },
): InstructionPermissions {
  const { globalRole } = useAuth();

  const isSuperadmin = globalRole === "superadmin";
  const isTenantAdmin = globalRole === "tenant_admin";
  const isMember = globalRole === "member";

  return {
    // ── Global base ────────────────────────────────────────
    // Только superadmin видит и редактирует глобальные инструкции
    canViewGlobalBase: isSuperadmin,
    canEditGlobalBase: isSuperadmin,
    canPublishGlobalBase: isSuperadmin,

    // ── Tenant overrides ───────────────────────────────────
    // Superadmin — полный доступ ко всем tenant overrides
    // Tenant admin — только своего tenant (scope через URL/API)
    canViewTenantOverrides: isSuperadmin || isTenantAdmin,
    canEditTenantOverride: isSuperadmin || isTenantAdmin,
    canActivateTenantOverride: isSuperadmin || isTenantAdmin,

    // ── Deal overrides ─────────────────────────────────────
    // Deal override доступен если есть capability canManageRequests
    // (проверяется через ProjectRouteGuard на уровне роута,
    //  здесь дополнительно для inline UI decisions)
    canViewDealOverrides:
      isSuperadmin ||
      isTenantAdmin ||
      (isMember && (dealCapabilities?.canManageRequests ?? false)),
    canEditDealOverride:
      isSuperadmin ||
      isTenantAdmin ||
      (isMember && (dealCapabilities?.canManageRequests ?? false)),
    canActivateDealOverride:
      isSuperadmin ||
      isTenantAdmin ||
      (isMember && (dealCapabilities?.canManageRequests ?? false)),

    // ── История ────────────────────────────────────────────
    // Любой авторизованный пользователь видит историю в своём scope
    canViewVersionHistory: !!globalRole,
  };
}


