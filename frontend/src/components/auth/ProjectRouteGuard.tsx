// =============================================================
// src/components/auth/ProjectRouteGuard.tsx
// Защита маршрутов проекта по capability-флагам.
// =============================================================

import React from "react";
import { Navigate, useParams } from "react-router-dom";
import { Lock } from "lucide-react";
import { useDealPermissions } from "../../hooks/usePermissions";
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
  const { dealId } = useParams<{ dealId: string }>();

  // ВАЖНО: хук вызываем всегда, даже если dealId ещё нет.
  // Внутри useDealPermissions нужно быть готовым к undefined/null.
  const dealPermissions = useDealPermissions(dealId as string);

  // Если нет dealId в URL — отправляем на список сделок.
  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  // Если capability не задан, считаем, что достаточно иметь доступ к overview проекта.
  if (!requiredCapability) {
    if (dealPermissions.canViewOverview) {
      return children;
    }
  } else if (dealPermissions[requiredCapability]) {
    return children;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-subtle)] px-4">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-6 py-6 text-center shadow-sm">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]">
          <Lock size={18} aria-hidden="true" />
        </div>

        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          Нет доступа
        </h1>

        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
          У вас нет прав для просмотра этой страницы. Обратитесь к
          администратору проекта, если считаете, что это ошибка.
        </p>

        <div className="mt-5 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => window.history.back()}
          >
            Назад
          </Button>
        </div>
      </div>
    </div>
  );
};

