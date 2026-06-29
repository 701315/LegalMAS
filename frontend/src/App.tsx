// src/App.tsx

import React from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";
import "./App.css";

// ── Marketing pages ───────────────────────────────────────────
import HomePage       from "./marketing/pages/HomePage";
import SecurityPage   from "./marketing/pages/SecurityPage";
import SolutionsPage  from "./marketing/pages/SolutionsPage";
import CapabilitiesPage from "./marketing/pages/CapabilitiesPage";
import TechOverviewPage from "./marketing/pages/TechOverviewPage";
import DemoPage       from "./marketing/pages/DemoPage";
import AboutPage      from "./marketing/pages/AboutPage";

// ── App pages ─────────────────────────────────────────────────
import LoginPage      from "./pages/LoginPage";
import DashboardPage  from "./pages/DashboardPage";
import DealPage       from "./pages/DealPage";
import DealListPage   from "./pages/DealListPage";
import NewProjectPage from "./pages/NewProjectPage";
import ProjectUploadPage  from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import DealPlaybookSelectorPage  from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage    from "./pages/AdminPlaybookLinesPage";
import ModelConfigsAdminPage     from "./pages/ModelConfigsAdminPage";
import AdminPlaybookVersionsPage from "./pages/AdminPlaybookVersionsPage";

// ── Utilities ─────────────────────────────────────────────────
import { shouldPollDealLanguageDiscovery } from "./utils/languageDiscovery";
import { useDeal }   from "./api/deals";
import { useAuth }   from "./hooks/useAuth";
import { ProjectRouteGuard } from "./components/auth/ProjectRouteGuard";
import ScrollToAnchor from "./components/routing/ScrollToAnchor";
import AppShell from "./components/layout/AppShell";

const POLL_INTERVAL = 4000;

// ─────────────────────────────────────────────────────────────
function DealRouteWrapper() {
  const { dealId } = useParams<{ dealId: string }>();
  const { data: deal, isLoading, isError, error } = useDeal(
    dealId ?? null,
    {
      refetchInterval: (query) =>
        shouldPollDealLanguageDiscovery(
          query.state.data?.language_discovery_status
        )
          ? POLL_INTERVAL
          : false,
    }
  );

  if (isLoading) return (
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

  if (isError || !deal) return (
    <div className="min-h-screen bg-[var(--bg-base)] px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            Не удалось загрузить проект
          </h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {error instanceof Error
              ? error.message
              : "Проект не найден или временно недоступен."}
          </p>
        </div>
      </div>
    </div>
  );

  return <DealPage deal={deal} />;
}

// ─────────────────────────────────────────────────────────────
function RequireAuth({ children }: { children: React.ReactElement }) {
  const { userId } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  return children;
}

function RequireSuperadmin({ children }: { children: React.ReactElement }) {
  const { userId, globalRole } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  if (globalRole !== "superadmin") return <Navigate to="/dashboard" replace />;
  return children;
}

function RequireAdminOrSuperadmin({ children }: { children: React.ReactElement }) {
  const { userId, globalRole } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  if (globalRole !== "superadmin" && globalRole !== "admin")
    return <Navigate to="/dashboard" replace />;
  return children;
}

// ─────────────────────────────────────────────────────────────
function App() {
  return (
    <div className="min-h-screen w-full bg-[var(--bg-base)] text-[var(--text-primary)]">
      <ScrollToAnchor />
      <Routes>

        {/* ── Public marketing routes ──────────────────────── */}
        <Route path="/"         element={<HomePage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/demo"     element={<DemoPage />} />
        <Route path="/about"    element={<AboutPage />} />

        {/* Legacy routes → redirect to new IA */}
        <Route path="/capabilities" element={<Navigate to="/platform" replace />} />
        <Route path="/tech"         element={<Navigate to="/platform" replace />} />
        <Route path="/solutions"    element={<Navigate to="/use-cases" replace />} />

        {/* Placeholder routes — страницы будут собраны следующим этапом */}
        <Route path="/platform"   element={<CapabilitiesPage />} />
        <Route path="/use-cases"  element={<SolutionsPage />} />

        {/* Auth entry point — контракт не меняется */}
        <Route path="/login" element={<LoginPage />} />

        {/* ── Protected app routes ─────────────────────────── */}
        <Route path="/dashboard" element={
          <RequireAuth><AppShell><DashboardPage /></AppShell></RequireAuth>
        }/>

        <Route path="/projects/:dealId" element={
          <RequireAuth><AppShell><DealRouteWrapper /></AppShell></RequireAuth>
        }/>

        <Route path="/projects/new" element={
          <RequireSuperadmin><AppShell><NewProjectPage /></AppShell></RequireSuperadmin>
        }/>

        <Route path="/deals" element={
          <RequireAuth><AppShell><DealListPage /></AppShell></RequireAuth>
        }/>

        <Route path="/projects/:dealId/upload" element={
          <RequireAuth>
            <AppShell>
              <ProjectRouteGuard requiredCapability="canUploadDocuments">
                <ProjectUploadPage />
              </ProjectRouteGuard>
            </AppShell>
          </RequireAuth>
        }/>

        <Route path="/projects/:dealId/members" element={
          <RequireAuth>
            <AppShell>
              <ProjectRouteGuard requiredCapability="canManageRequests">
                <ProjectMembersPage />
              </ProjectRouteGuard>
            </AppShell>
          </RequireAuth>
        }/>

        <Route path="/projects/:dealId/playbook" element={
          <RequireAuth>
            <AppShell>
              <ProjectRouteGuard requiredCapability="canViewOverview">
                <DealPlaybookSelectorPage />
              </ProjectRouteGuard>
            </AppShell>
          </RequireAuth>
        }/>

        <Route path="/projects/:dealId/playbooks/admin" element={
          <RequireAuth>
            <AppShell>
              <ProjectRouteGuard requiredCapability="canManageRequests">
                <AdminPlaybookLinesPage />
              </ProjectRouteGuard>
            </AppShell>
          </RequireAuth>
        }/>

        <Route path="/admin/model-configs" element={
          <RequireAdminOrSuperadmin>
            <AppShell><ModelConfigsAdminPage /></AppShell>
          </RequireAdminOrSuperadmin>
        }/>

        <Route path="/admin/playbook-versions" element={
          <RequireAdminOrSuperadmin>
            <AppShell><AdminPlaybookVersionsPage /></AppShell>
          </RequireAdminOrSuperadmin>
        }/>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;




