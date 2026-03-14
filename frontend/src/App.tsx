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
// Старую YAML-страницу оставляем в проекте, но не используем по default-роуту
// import ProjectPlaybookPage from "./pages/ProjectPlaybookPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import { ProjectRouteGuard } from "./components/auth/ProjectRouteGuard";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage from "./pages/AdminPlaybookLinesPage";



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

        {/* Страница загрузки документов: capability canUploadDocuments */}
        <Route
          path="/projects/:dealId/upload"
          element={
            <RequireAuth>
              <ProjectRouteGuard requiredCapability="canUploadDocuments">
                <ProjectUploadPage />
              </ProjectRouteGuard>
            </RequireAuth>
          }
        />

        {/* Страница участников проекта */}
        <Route
          path="/projects/:dealId/members"
          element={
            <RequireAuth>
              <ProjectRouteGuard requiredCapability="canManageRequests">
                <ProjectMembersPage />
              </ProjectRouteGuard>
            </RequireAuth>
          }
        />

        {/* Новая страница playbook: выбор/привязка версии к проекту */}
        <Route
          path="/projects/:dealId/playbook"
          element={
            <RequireAuth>
              <ProjectRouteGuard requiredCapability="canViewOverview">
                <DealPlaybookSelectorPage />
              </ProjectRouteGuard>
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

        {/* Конструктор шаблонов playbook в контексте проекта (admin/editor) */}
        <Route
          path="/projects/:dealId/playbooks/admin"
          element={
            <RequireAuth>
              <ProjectRouteGuard requiredCapability="canManageRequests">
                <AdminPlaybookLinesPage />
              </ProjectRouteGuard>
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
