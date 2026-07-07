// =============================================================
// src/services/permissions/permissions.types.ts
// Типы для системы прав по сделке.
// =============================================================

import type { ProjectRole } from "../../api/auth";
import type { GlobalRole } from "../../stores/uiStore";


export interface PermissionsContext {
  /**
   * Системная роль пользователя.
   *
   * Может быть null, если пользователь не залогинен или user-info ещё
   * не подгружена в store (см. useUIStore.globalRole: GlobalRole | null).
   * getDealPermissions обязан обработать null как "нет прав".
   */
  userRole: GlobalRole | null;
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
