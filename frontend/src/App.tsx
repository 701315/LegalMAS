// =============================================================
// src/App.tsx
// Основное приложение LegalMAS фронта: Login -> Dashboard -> Project.
// =============================================================

import React from "react";
import "./App.css";
import {
  Routes,
  Route,
  Navigate,
  useParams,
  useNavigate,
} from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DealPage from "./pages/DealPage";
import DealListPage from "./pages/DealListPage"; // временно, если нужно
import DashboardPage from "./pages/DashboardPage";
import NewProjectPage from "./pages/NewProjectPage";
import { useDeal } from "./api/deals";
import { useAuth } from "./hooks/useAuth";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectPlaybookPage from "./pages/ProjectPlaybookPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";

// Временная обёртка для страницы проекта (используем существующий DealPage)
function DealRouteWrapper() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const { data: deal, isLoading } = useDeal(dealId ?? null);

  const handleBackToDashboard = () => {
    navigate("/dashboard");
  };

  if (isLoading || !deal) {
    return (
      <div className="p-6 text-center text-gray-500">
        Загружаем данные проекта…
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 pt-4">
        <button
          type="button"
          onClick={handleBackToDashboard}
          className="text-sm text-blue-600 hover:underline"
        >
          ← Вернуться к списку проектов
        </button>
      </div>
      <DealPage deal={deal} />
    </div>
  );
}

// Простая защита маршрутов: требует авторизации
function RequireAuth({ children }: { children: React.ReactElement }) {
  const { userId } = useAuth();
  if (!userId) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

// Защита маршрута только для superadmin
function RequireSuperadmin({
  children,
}: {
  children: React.ReactElement;
}) {
  const { userId, globalRole } = useAuth();
  if (!userId) {
    return <Navigate to="/login" replace />;
  }
  if (globalRole !== "superadmin") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

// Защита маршрутов проекта по роли в проекте
function RequireProjectRole({
  children,
  allowedRoles,
}: {
  children: React.ReactElement;
  allowedRoles: Array<"admin" | "editor" | "viewer">;
}) {
  const { projectRoles } = useAuth();
  const { dealId } = useParams<{ dealId: string }>();

  if (!dealId) {
    return <Navigate to="/dashboard" replace />;
  }

  const role = projectRoles[dealId] ?? "viewer";

  if (!allowedRoles.includes(role)) {
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
  }

  return children;
}

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
        {/* Экран логина */}
        <Route path="/login" element={<LoginPage />} />

        {/* Дашборд доступен только после логина */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />

        {/* Страница проекта (используем старый DealPage по новому пути) */}
        <Route
          path="/projects/:dealId"
          element={
            <RequireAuth>
              <DealRouteWrapper />
            </RequireAuth>
          }
        />

        {/* Создание нового проекта — только для superadmin */}
        <Route
          path="/projects/new"
          element={
            <RequireSuperadmin>
              <NewProjectPage />
            </RequireSuperadmin>
          }
        />

        {/* Временный маршрут для старого списка сделок (если нужно оставить) */}
        <Route
          path="/deals"
          element={
            <RequireAuth>
              <DealListPage />
            </RequireAuth>
          }
        />

        {/* Страница загрузки документов: admin + editor */}
        <Route
          path="/projects/:dealId/upload"
          element={
            <RequireAuth>
              <RequireProjectRole allowedRoles={["admin", "editor"]}>
                <ProjectUploadPage />
              </RequireProjectRole>
            </RequireAuth>
          }
        />

        {/* Страница участников проекта: только admin */}
        <Route
          path="/projects/:dealId/members"
          element={
            <RequireAuth>
              <RequireProjectRole allowedRoles={["admin"]}>
                <ProjectMembersPage />
              </RequireProjectRole>
            </RequireAuth>
          }
        />

        {/* Страница playbook: admin + editor */}
        <Route
          path="/projects/:dealId/playbook"
          element={
            <RequireAuth>
              <RequireProjectRole allowedRoles={["admin", "editor"]}>
                <ProjectPlaybookPage />
              </RequireProjectRole>
            </RequireAuth>
          }
        />

        {/* Корень: авторизованных на /dashboard, остальных на /login */}
        <Route
          path="/"
          element={
            <RequireAuth>
              <Navigate to="/dashboard" replace />
            </RequireAuth>
          }
        />

        {/* Fallback: на неизвестные пути отправляем на корень */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;
