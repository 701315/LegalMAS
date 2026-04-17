// =============================================================
// src/App.tsx
// Основное приложение LegalMAS фронта:
// Landing -> Login -> Dashboard -> Project.
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
import LandingPage from "./pages/LandingPage";
import DealPage from "./pages/DealPage";
import DealListPage from "./pages/DealListPage";
import DashboardPage from "./pages/DashboardPage";
import NewProjectPage from "./pages/NewProjectPage";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage from "./pages/AdminPlaybookLinesPage";
import ModelConfigsAdminPage from "./pages/ModelConfigsAdminPage";
import AdminPlaybookVersionsPage from "./pages/AdminPlaybookVersionsPage";
import SecurityPage from "./pages/SecurityPage";
import TechOverviewPage from "./pages/TechOverviewPage";
import SolutionsPage from "./pages/SolutionsPage";
import DemoPage from "./pages/DemoPage";
import AboutPage from "./pages/AboutPage";
import CapabilitiesPage from "./pages/CapabilitiesPage";

import { useDeal } from "./api/deals";
import { useAuth } from "./hooks/useAuth";
import { ProjectRouteGuard } from "./components/auth/ProjectRouteGuard";
import ScrollToAnchor from "./components/routing/ScrollToAnchor";

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

  if (!userId) {
    return <Navigate to="/login" replace />;
  }

  if (globalRole !== "superadmin") {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

// Защита маршрута для admin или superadmin
function RequireAdminOrSuperadmin({
  children,
}: {
  children: React.ReactElement;
}) {
  const { userId, globalRole } = useAuth();

  if (!userId) {
    return <Navigate to="/login" replace />;
  }

  if (globalRole !== "superadmin" && globalRole !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

function App() {
  return (
    <div className="min-h-screen w-full">
      {/* Глобальный обработчик якорей */}
      <ScrollToAnchor />

      <Routes>
        {/* ── Публичные маршруты (без авторизации) ────────── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/tech" element={<TechOverviewPage />} />
        <Route path="/solutions" element={<SolutionsPage />} />
        <Route path="/capabilities" element={<CapabilitiesPage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/about" element={<AboutPage />} />

        {/* ── Защищённые маршруты ──────────────────────────── */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId"
          element={
            <RequireAuth>
              <DealRouteWrapper />
            </RequireAuth>
          }
        />

        <Route
          path="/projects/new"
          element={
            <RequireSuperadmin>
              <NewProjectPage />
            </RequireSuperadmin>
          }
        />

        <Route
          path="/deals"
          element={
            <RequireAuth>
              <DealListPage />
            </RequireAuth>
          }
        />

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
        <Route
          path="/admin/model-configs"
          element={
            <RequireAdminOrSuperadmin>
              <ModelConfigsAdminPage />
            </RequireAdminOrSuperadmin>
          }
        />

        <Route
          path="/admin/playbook-versions"
          element={
            <RequireAdminOrSuperadmin>
              <AdminPlaybookVersionsPage />
            </RequireAdminOrSuperadmin>
          }
        />

        {/* ── Fallback ─────────────────────────────────────── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;

