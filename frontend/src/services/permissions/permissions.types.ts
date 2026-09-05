// =============================================================
// src/services/permissions/permissions.types.ts
// Types for the deal-level permissions system.
// =============================================================

import type { ProjectRole } from "../../api/auth";
import type { GlobalRole } from "../../stores/uiStore";

export interface PermissionsContext {
  /**
   * User's system-level role.
   *
   * May be null if the user is not authenticated or user-info
   * has not yet been loaded into store (see useUIStore.globalRole: GlobalRole | null).
   * getDealPermissions must treat null as "no permissions".
   */
  userRole: GlobalRole | null;
  projectRole?: ProjectRole | null;
  // Additional fields (orgId, scopes, etc.) can be added here if needed
}

export interface DealPermissions {
  // Access to deal information
  canViewOverview: boolean;
  // Launching analysis runs
  canStartRun: boolean;
  // Viewing classification report
  canViewClassificationReport: boolean;
  // Viewing audit log
  canViewAuditLog: boolean;
  // Document operations
  canViewDocuments: boolean;
  canDownloadDocuments: boolean;
  canReclassifyDocuments: boolean;
  canDeleteDocuments: boolean;
  // DD requests management
  canManageRequests: boolean;
  // Document upload
  canUploadDocuments: boolean;
}


