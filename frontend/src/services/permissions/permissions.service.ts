// =============================================================
// src/services/permissions/permissions.service.ts
// Логика вычисления прав из глобальной и проектной ролей.
// =============================================================

import type { DealPermissions, PermissionsContext } from "./permissions.types";

/**
 * Базовая матрица прав на уровне security‑ролей пользователя (глобальная роль).
 * Здесь не учитывается принадлежность к конкретному проекту.
 */
function basePermissionsByUserRole(
  userRole: PermissionsContext["userRole"],
): DealPermissions {
  const isSuperAdmin = userRole === "superadmin";
  const isAdmin = userRole === "admin";
  const isReviewer = userRole === "reviewer";
  const isEditor = userRole === "editor";
  // Глобальные роли "user"/"system" трактуем как viewer по матрице прав
  const isViewer =
    userRole === "viewer" || userRole === "user" || userRole === "system";

  const canViewDocs =
    isSuperAdmin || isAdmin || isReviewer || isEditor || isViewer;

  // Superadmin — полный доступ ко всем действиям в системе.
  // Это «системный бог», его права не должны ограничиваться projectRole.
  if (isSuperAdmin) {
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

  if (isAdmin || isEditor || isReviewer || isViewer) {
    return {
      canViewOverview: canViewDocs,
      // Запуск анализов — только admin/editor.
      canStartRun: isAdmin || isEditor,
      // Отчёты и аудит‑лог — admin + reviewer.
      canViewClassificationReport: isAdmin || isReviewer,
      canViewAuditLog: isAdmin || isReviewer,
      // Документы видят все роли, включая viewer.
      canViewDocuments: canViewDocs,
      // Операции с документами — admin/editor.
      canDownloadDocuments: isAdmin || isEditor,
      canReclassifyDocuments: isAdmin || isEditor,
      canDeleteDocuments: isAdmin || isEditor,
      // Управление запросами — admin/editor.
      canManageRequests: isAdmin || isEditor,
      // Загрузка документов — admin/editor.
      canUploadDocuments: isAdmin || isEditor,
    };
  }

  // На случай, если в будущем появится новая роль и её забудут добавить:
  // по умолчанию всё запрещено, кроме чтения overview/documents.
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
 * Учитываем и глобальную security‑роль, и роль в конкретном проекте.
 *
 * Инварианты:
 * - superadmin имеет полный доступ ко всем проектам, projectRole игнорируем;
 * - projectRole может только УРЕЗАТЬ глобальные права, но не расширять их;
 * - viewer в проекте всегда read‑only по сделке, даже если глобально он admin/editor.
 */
export function getDealPermissions(ctx: PermissionsContext): DealPermissions {
  const base = basePermissionsByUserRole(ctx.userRole);

  // superadmin — полный доступ во всех проектах, ограничения projectRole не применяем.
  if (ctx.userRole === "superadmin") {
    return base;
  }

  const projectRole = ctx.projectRole ?? "viewer";
  const projectIsAdminOrEditor =
    projectRole === "admin" || projectRole === "editor";
  const projectIsViewer = projectRole === "viewer";

  // В проекте viewer — только чтение, без разрушающих действий,
  // но возможность смотреть отчёты/аудит‑лог оставляем согласно глобальной роли.
  if (projectIsViewer) {
    return {
      ...base,
      canViewOverview: true,
      canStartRun: false,
      canViewClassificationReport: base.canViewClassificationReport,
      canViewAuditLog: base.canViewAuditLog,
      canViewDocuments: true,
      canDownloadDocuments: false,
      canReclassifyDocuments: false,
      canDeleteDocuments: false,
      canManageRequests: false,
      canUploadDocuments: false,
    };
  }

  // Для admin/editor в проекте — пересекаем с глобальными правами.
  // Если глобальная роль что‑то запрещает, projectRole не может это разрешить.
  return {
    ...base,
    canStartRun: base.canStartRun && projectIsAdminOrEditor,
    canDownloadDocuments:
      base.canDownloadDocuments && projectIsAdminOrEditor,
    canReclassifyDocuments:
      base.canReclassifyDocuments && projectIsAdminOrEditor,
    canDeleteDocuments: base.canDeleteDocuments && projectIsAdminOrEditor,
    canManageRequests: base.canManageRequests && projectIsAdminOrEditor,
    canUploadDocuments: base.canUploadDocuments && projectIsAdminOrEditor,
  };
}
