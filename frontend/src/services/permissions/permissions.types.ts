// =============================================================
// src/services/permissions/permissions.types.ts
// Типы для системы прав по сделке.
// =============================================================

import type { ProjectRole } from "../../api/auth";
import type { GlobalRole } from "../../stores/uiStore";


export interface PermissionsContext {
  userRole: GlobalRole;
  projectRole?: ProjectRole | null;
  // при необходимости сюда можно добавить ещё поля (orgId, scopes и т.п.)
}

export interface DealPermissions {
  // Доступ к информации по сделке
  canViewOverview: boolean;
  // Запуск анализа (runs)
  canStartRun: boolean;
  // Просмотр отчёта по классификации
  canViewClassificationReport: boolean;
  // Просмотр журнала аудита
  canViewAuditLog: boolean;
  // Работа с документами
  canViewDocuments: boolean;
  canDownloadDocuments: boolean;
  canReclassifyDocuments: boolean;
  canDeleteDocuments: boolean;
  // Работа с DD-запросами
  canManageRequests: boolean;
  // Загрузка документов
  canUploadDocuments: boolean;
}
