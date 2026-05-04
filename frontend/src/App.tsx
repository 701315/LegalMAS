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
import AppShell from "./components/layout/AppShell";

function DealRouteWrapper() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const { data: deal, isLoading } = useDeal(dealId ?? null);

  const handleBackToDashboard = () => {
    navigate("/dashboard");
  };

  if (isLoading || !deal) {
    return (
      <div className="min-h-screen bg-[var(--bg-base)] px-6 py-10">
        <div className="mx-auto max-w-7xl animate-fadein">
          <div className="skeleton h-5 w-48" />
          <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
            <div className="skeleton mb-4 h-6 w-64" />
            <div className="skeleton mb-3 h-4 w-full" />
            <div className="skeleton mb-3 h-4 w-11/12" />
            <div className="skeleton h-4 w-9/12" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4">
        <button
          type="button"
          onClick={handleBackToDashboard}
          className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] shadow-sm transition-all duration-150 hover:border-[var(--border-strong)] hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
        >
          ← Вернуться к списку проектов
        </button>
      </div>
      <DealPage deal={deal} />
    </>
  );
}

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { userId } = useAuth();

  if (!userId) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

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
    <div className="min-h-screen w-full bg-[var(--bg-base)] text-[var(--text-primary)]">
      <ScrollToAnchor />

      <Routes>
        {/* Публичные маршруты (без AppShell) */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/tech" element={<TechOverviewPage />} />
        <Route path="/solutions" element={<SolutionsPage />} />
        <Route path="/capabilities" element={<CapabilitiesPage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/about" element={<AboutPage />} />

        {/* Защищённые маршруты с общим AppShell */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <AppShell>
                <DashboardPage />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId"
          element={
            <RequireAuth>
              <AppShell>
                <DealRouteWrapper />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/new"
          element={
            <RequireSuperadmin>
              <AppShell>
                <NewProjectPage />
              </AppShell>
            </RequireSuperadmin>
          }
        />

        <Route
          path="/deals"
          element={
            <RequireAuth>
              <AppShell>
                <DealListPage />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId/upload"
          element={
            <RequireAuth>
              <AppShell>
                <ProjectRouteGuard requiredCapability="canUploadDocuments">
                  <ProjectUploadPage />
                </ProjectRouteGuard>
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId/members"
          element={
            <RequireAuth>
              <AppShell>
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <ProjectMembersPage />
                </ProjectRouteGuard>
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId/playbook"
          element={
            <RequireAuth>
              <AppShell>
                <ProjectRouteGuard requiredCapability="canViewOverview">
                  <DealPlaybookSelectorPage />
                </ProjectRouteGuard>
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/projects/:dealId/playbooks/admin"
          element={
            <RequireAuth>
              <AppShell>
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <AdminPlaybookLinesPage />
                </ProjectRouteGuard>
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/admin/model-configs"
          element={
            <RequireAdminOrSuperadmin>
              <AppShell>
                <ModelConfigsAdminPage />
              </AppShell>
            </RequireAdminOrSuperadmin>
          }
        />

        <Route
          path="/admin/playbook-versions"
          element={
            <RequireAdminOrSuperadmin>
              <AppShell>
                <AdminPlaybookVersionsPage />
              </AppShell>
            </RequireAdminOrSuperadmin>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;
