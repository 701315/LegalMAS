// =============================================================
// src/components/auth/ProjectRouteGuard.tsx
// Защита маршрутов проекта по capability-флагам.
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
   * Какой capability требуется для доступа к странице.
   * Если не указан — пускаем по факту наличия projectRole (viewer и выше).
   */
  requiredCapability?: RequiredCapability;
  children: React.ReactElement;
}

/**
 * Обёртка для маршрутов проекта.
 * Берёт dealId из URL, вычисляет permissions через useDealPermissions
 * и проверяет нужный capability. Если capability отсутствует — показывает "Нет доступа".
 */
export const ProjectRouteGuard: React.FC<ProjectRouteGuardProps> = ({
  requiredCapability,
  children,
}) => {
  const { t } = useTranslation("common");
  const { dealId } = useParams<{ dealId: string }>();

  // ВАЖНО: хук вызываем всегда, даже если dealId ещё нет.
  // Внутри useDealPermissions нужно быть готовым к undefined/null.
  const globalRole = useUIStore((s) => s.globalRole);
  const dealPermissions = useDealPermissions(dealId as string);

  // Если нет dealId в URL — отправляем на список сделок.
  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  // Защита от null globalRole.
  // globalRole === null означает что store ещё не гидратирован
  // (пользователь только что залогинился или открыл новую вкладку).
  // Не блокируем доступ — показываем spinner пока данные не появятся.
  if (globalRole === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg-subtle)]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent-primary)]" />
      </div>
    );
  }

  // Проверяем capability.
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



