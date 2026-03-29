// =============================================================
// src/components/auth/ProjectRouteGuard.tsx
// Защита маршрутов проекта по capability-флагам.
// =============================================================

import React from "react";
import { useParams, Navigate } from "react-router-dom";
import { useDealPermissions } from "../../hooks/usePermissions";

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

  // Если нужного права нет — показываем экран "Нет доступа".
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white border rounded-lg px-6 py-4 text-center max-w-sm">
        <h1 className="text-lg font-semibold text-gray-900 mb-2">
          Нет доступа
        </h1>
        <p className="text-sm text-gray-600 mb-4">
          У вас нет прав для просмотра этой страницы. Обратитесь к
          администратору проекта, если считаете, что это ошибка.
        </p>
      </div>
    </div>
  );
};
