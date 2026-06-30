// =============================================================
// src/services/permissions/permissions.service.ts
// Логика вычисления прав из системной и проектной ролей.
// =============================================================

import type { DealPermissions, PermissionsContext } from "./permissions.types";

/**
 * Базовая матрица прав на уровне системной роли пользователя.
 * Здесь не учитывается принадлежность к конкретному проекту.
 *
 * Системные роли:
 * - superadmin   : полный доступ везде
 * - tenant_admin : полный доступ в рамках своего tenant'а
 * - member       : доступ только через project role
 */
function basePermissionsByUserRole(
  userRole: PermissionsContext["userRole"],
): DealPermissions {
  // superadmin и tenant_admin имеют полный базовый доступ.
  // Разница между ними — на уровне tenant scope, а не на уровне capability.
  if (userRole === "superadmin" || userRole === "tenant_admin") {
    return {
      canViewOverview: true,
      canStartRun: true,
      canViewClassificationReport: true,
      canViewAuditLog: true,
      canViewDocuments: true,
      canDownloadDocuments: true,
      canReclassifyDocuments: true,
      canDeleteDocuments: true,
      canManageRequests: true,
      canUploadDocuments: true,
    };
  }

  // member — базовый read-only доступ.
  // Реальные project-specific права определяются ниже через project role.
  return {
    canViewOverview: true,
    canStartRun: false,
    canViewClassificationReport: false,
    canViewAuditLog: false,
    canViewDocuments: true,
    canDownloadDocuments: false,
    canReclassifyDocuments: false,
    canDeleteDocuments: false,
    canManageRequests: false,
    canUploadDocuments: false,
  };
}

/**
 * Вычислить итоговые права пользователя по конкретной сделке.
 *
 * Логика:
 * - superadmin   → полный доступ, projectRole не применяется
 * - tenant_admin → полный доступ к проектам своего tenant'а,
 *                  projectRole не применяется
 * - member       → права определяются исключительно project role:
 *                  admin/editor → расширенные права
 *                  viewer       → только чтение
 */
export function getDealPermissions(ctx: PermissionsContext): DealPermissions {
  const base = basePermissionsByUserRole(ctx.userRole);

  // superadmin — полный доступ везде.
  if (ctx.userRole === "superadmin") {
    return base;
  }

  // tenant_admin — полный доступ ко всем проектам своего tenant'а.
  // На frontend projectRole не должен ограничивать tenant_admin.
  if (ctx.userRole === "tenant_admin") {
    return base;
  }

  // Для member права определяются project role.
  const projectRole = ctx.projectRole ?? "viewer";
  const projectIsAdminOrEditor =
    projectRole === "admin" || projectRole === "editor";
  const projectIsViewer = projectRole === "viewer";

  // viewer в проекте — только чтение
  if (projectIsViewer) {
    return {
      canViewOverview: true,
      canStartRun: false,
      canViewClassificationReport: false,
      canViewAuditLog: false,
      canViewDocuments: true,
      canDownloadDocuments: false,
      canReclassifyDocuments: false,
      canDeleteDocuments: false,
      canManageRequests: false,
      canUploadDocuments: false,
    };
  }

  // admin/editor в проекте — доступ по project role
  return {
    canViewOverview: true,
    canStartRun: projectIsAdminOrEditor,
    canViewClassificationReport: projectIsAdminOrEditor,
    canViewAuditLog: projectIsAdminOrEditor,
    canViewDocuments: true,
    canDownloadDocuments: projectIsAdminOrEditor,
    canReclassifyDocuments: projectIsAdminOrEditor,
    canDeleteDocuments: projectIsAdminOrEditor,
    canManageRequests: projectIsAdminOrEditor,
    canUploadDocuments: projectIsAdminOrEditor,
  };
}