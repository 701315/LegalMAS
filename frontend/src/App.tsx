// =============================================================
// src/App.tsx
// Основное приложение LegalMAS фронта: Landing -> Login -> Dashboard -> Project.
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
import LandingPage from "./pages/LandingPage";       // ← ДОБАВЛЕНО
import DealPage from "./pages/DealPage";
import DealListPage from "./pages/DealListPage";
import DashboardPage from "./pages/DashboardPage";
import NewProjectPage from "./pages/NewProjectPage";
import { useDeal } from "./api/deals";
import { useAuth } from "./hooks/useAuth";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import { ProjectRouteGuard } from "./components/auth/ProjectRouteGuard";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage from "./pages/AdminPlaybookLinesPage";
import ModelConfigsAdminPage from "./pages/ModelConfigsAdminPage";
import AdminPlaybookVersionsPage from "./pages/AdminPlaybookVersionsPage";


// Временная обёртка для страницы проекта
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
function RequireSuperadmin({ children }: { children: React.ReactElement }) {
  const { userId, globalRole } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  if (globalRole !== "superadmin") return <Navigate to="/dashboard" replace />;
  return children;
}


// Защита маршрута для admin или superadmin
function RequireAdminOrSuperadmin({ children }: { children: React.ReactElement }) {
  const { userId, globalRole } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  if (globalRole !== "superadmin" && globalRole !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}


function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>

        {/* ── Публичные маршруты (без авторизации) ────────── */}

        {/* Лендинг — первая страница при открытии приложения */}
        <Route path="/" element={<LandingPage />} />        {/* ← ИЗМЕНЕНО */}

        {/* Экран логина */}
        <Route path="/login" element={<LoginPage />} />


        {/* ── Защищённые маршруты ──────────────────────────── */}

        {/* Дашборд */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />

        {/* Страница проекта */}
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

        {/* Временный маршрут для старого списка сделок */}
        <Route
          path="/deals"
          element={
            <RequireAuth>
              <DealListPage />
            </RequireAuth>
          }
        />

        {/* Загрузка документов */}
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

        {/* Участники проекта */}
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

        {/* Привязка версии плейбука к проекту */}
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

        {/* Конструктор шаблонов playbook */}
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

        {/* ── Админ-маршруты ───────────────────────────────── */}

        {/* Профили моделей */}
        <Route
          path="/admin/model-configs"
          element={
            <RequireAdminOrSuperadmin>
              <ModelConfigsAdminPage />
            </RequireAdminOrSuperadmin>
          }
        />

        {/* Версии плейбуков */}
        <Route
          path="/admin/playbook-versions"
          element={
            <RequireAdminOrSuperadmin>
              <AdminPlaybookVersionsPage />
            </RequireAdminOrSuperadmin>
          }
        />

        {/* ── Fallback ─────────────────────────────────────── */}

        {/* Любой неизвестный путь → на лендинг */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </div>
  );
}

export default App;
