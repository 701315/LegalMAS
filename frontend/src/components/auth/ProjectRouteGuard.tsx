// =============================================================
// src/components/auth/ProjectRouteGuard.tsx
// Project route protection based on capability flags.
// =============================================================

import React from "react";
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useUIStore } from "../../stores/uiStore";
import Button from "../ui/Button";

type RequiredCapability =
  | "canViewOverview"
  | "canStartRun"
  | "canViewClassificationReport"
  | "canViewAuditLog"
  | "canViewDocuments"
  | "canDownloadDocuments"
  | "canReclassifyDocuments"
  | "canDeleteDocuments"
  | "canManageRequests"
  | "canUploadDocuments";

interface ProjectRouteGuardProps {
  /**
   * The specific capability required to access the page.
   * If omitted, access is allowed based on projectRole (viewer and above).
   */
  requiredCapability?: RequiredCapability;
  children: React.ReactElement;
}

/**
 * Wrapper for project routes.
 * Extracts dealId from the URL, determines permissions via useDealPermissions,
 * and validates the required capability. Displays "Access Denied" if missing.
 */
export const ProjectRouteGuard: React.FC<ProjectRouteGuardProps> = ({
  requiredCapability,
  children,
}) => {
  const { t } = useTranslation("common");
  const { dealId } = useParams<{ dealId: string }>();

  // CRITICAL: The hook must always be called, even if dealId is not yet available.
  // useDealPermissions handles undefined/null internally.
  const globalRole = useUIStore((s) => s.globalRole);
  const dealPermissions = useDealPermissions(dealId as string);

  // If there is no dealId in the URL, redirect to the projects list.
  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  // Protect against null globalRole.
  // globalRole === null means the store is not yet hydrated
  // (the user just logged in or opened a new tab).
  // Do not block access — show a spinner until the state is loaded.
  if (globalRole === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg-subtle)]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent-primary)]" />
      </div>
    );
  }

  // Verify capability access.
  const hasAccess = !requiredCapability
    ? dealPermissions.canViewOverview
    : dealPermissions[requiredCapability];

  if (hasAccess) {
    return children;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-subtle)] px-4">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-6 py-6 text-center shadow-sm">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]">
          <Lock size={18} aria-hidden="true" />
        </div>

        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          {t("accessDenied.title")}
        </h1>

        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
          {t("accessDenied.message")}
        </p>

        <div className="mt-5 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => window.history.back()}
          >
            {t("actions.back")}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProjectRouteGuard;


