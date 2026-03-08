// =============================================================
// src/components/auth/ProjectRouteGuard.tsx
// Простая защита маршрутов проекта по роли (admin/editor/viewer).
// =============================================================

import React from "react";
import { useParams, Navigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

interface ProjectRouteGuardProps {
  /** Какие роли имеют доступ к странице. Если не указано — любая роль. */
  allowedRoles?: Array<"admin" | "editor" | "viewer">;
  children: React.ReactElement;
}

/**
 * Обёртка для маршрутов проекта.
 * Берёт dealId из URL, смотрит роль пользователя в этом проекте
 * и, если роли нет в allowedRoles, показывает страницу "Нет доступа".
 */
export const ProjectRouteGuard: React.FC<ProjectRouteGuardProps> = ({
  allowedRoles,
  children,
}) => {
  const { dealId } = useParams<{ dealId: string }>();
  const { projectRoles } = useAuth();

  // Если нет dealId в URL — считаем, что это ошибка маршрута.
  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  const role = projectRoles[dealId] ?? "viewer";

  // Если список allowedRoles не задан — пускаем всех.
  if (!allowedRoles || allowedRoles.includes(role)) {
    return children;
  }

  // Если роли не хватает — показываем простую страницу "Нет доступа".
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white border rounded-lg px-6 py-4 text-center max-w-sm">
        <h1 className="text-lg font-semibold text-gray-900 mb-2">
          Нет доступа
        </h1>
        <p className="text-sm text-gray-600 mb-4">
          У вас нет прав для просмотра этой страницы. Обратитесь к администратору
          проекта, если считаете, что это ошибка.
        </p>
      </div>
    </div>
  );
};
