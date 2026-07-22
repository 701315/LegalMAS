// src/App.tsx

import React from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";
import "./App.css";

// ── Marketing pages ───────────────────────────────────────────
import HomePage from "./marketing/pages/HomePage";
import SecurityPage from "./marketing/pages/SecurityPage";
import CapabilitiesPage from "./marketing/pages/CapabilitiesPage";
import DemoPage from "./marketing/pages/DemoPage";
import AboutPage from "./marketing/pages/AboutPage";

// ── Solution pages ────────────────────────────────────────────
import MaDueDiligencePage from "./marketing/pages/solutions/MaDueDiligencePage";
import ContractReviewPage from "./marketing/pages/solutions/ContractReviewPage";
import CompliancePage from "./marketing/pages/solutions/CompliancePage";
import InternalAuditPage from "./marketing/pages/solutions/InternalAuditPage";
import LawFirmsPage from "./marketing/pages/solutions/LawFirmsPage";
import CorporateLegalPage from "./marketing/pages/solutions/CorporateLegalPage";
import AuditCompliancePage from "./marketing/pages/solutions/AuditCompliancePage";
import CounterpartiesPage from "./marketing/pages/solutions/CounterpartiesPage";
import RealEstatePage from "./marketing/pages/solutions/RealEstatePage";

// ── App pages — существующие ──────────────────────────────────
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import DealPage from "./pages/DealPage";
import DealListPage from "./pages/DealListPage";
import NewProjectPage from "./pages/NewProjectPage";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage from "./pages/AdminPlaybookLinesPage";
import ModelConfigsAdminPage from "./pages/ModelConfigsAdminPage";
import AdminPlaybookVersionsPage from "./pages/AdminPlaybookVersionsPage";
import AdminPage from "./pages/AdminPage";
import TenantAdminPage from "./pages/TenantAdminPage";
import AdminTenantNewPage from "./pages/AdminTenantNewPage";
import AdminTenantDetailPage from "./pages/AdminTenantDetailPage";

// ── Instructions — global playbooks (superadmin) ──────────────
import InstructionsIndexPage from "./pages/instructions/InstructionsIndexPage";
import GlobalPlaybooksPage from "./pages/instructions/GlobalPlaybooksPage";
import GlobalPlaybookDetailPage from "./pages/instructions/GlobalPlaybookDetailPage";
import PlaybookVersionDetailPage from "./pages/instructions/PlaybookVersionDetailPage";

// ── Instructions — global checks lifecycle (superadmin) ───────
import GlobalInstructionsPage from "./pages/instructions/GlobalInstructionsPage";
import GlobalInstructionDetailPage from "./pages/instructions/GlobalInstructionDetailPage";
import GlobalInstructionVersionDetailPage from "./pages/instructions/GlobalInstructionVersionDetailPage";

// ── Instructions — doc-type (superadmin) ──────────────────────
import DocTypeInstructionsPage from "./pages/instructions/DocTypeInstructionsPage";
import DocTypeDetailPage from "./pages/instructions/DocTypeDetailPage";
import DocTypeVersionDetailPage from "./pages/instructions/DocTypeVersionDetailPage";

// ── Instructions — tenant-level (tenant_admin) ────────────────
import TenantInstructionsPage from "./pages/tenant-instructions/TenantInstructionsPage";
import TenantOverridesPage from "./pages/tenant-instructions/TenantOverridesPage";
import TenantOverrideDetailPage from "./pages/tenant-instructions/TenantOverrideDetailPage";

// ── Instructions — deal-level (project member) ────────────────
import DealInstructionsPage from "./pages/deal-instructions/DealInstructionsPage";
import DealOverridesPage from "./pages/deal-instructions/DealOverridesPage";
import DealOverrideDetailPage from "./pages/deal-instructions/DealOverrideDetailPage";

// ── Utilities ─────────────────────────────────────────────────
import { shouldPollDealLanguageDiscovery } from "./utils/languageDiscovery";
import { useDeal } from "./api/deals";
import { useAuth } from "./hooks/useAuth";
import { ProjectRouteGuard } from "./components/auth/ProjectRouteGuard";
import ScrollToAnchor from "./components/routing/ScrollToAnchor";
import AppShell from "./components/layout/AppShell";
import { ContactModalProvider } from "./marketing/context/ContactModalContext";

const POLL_INTERVAL = 4000;

// ─────────────────────────────────────────────────────────────
// Deal wrapper
// ─────────────────────────────────────────────────────────────

function DealRouteWrapper() {
  const { dealId } = useParams<{ dealId: string }>();
  const {
    data: deal,
    isLoading,
    isError,
    error,
  } = useDeal(dealId ?? null, {
    refetchInterval: (query) =>
      shouldPollDealLanguageDiscovery(
        query.state.data?.language_discovery_status,
      )
        ? POLL_INTERVAL
        : false,
  });

  if (isLoading) return <div>Loading...</div>;

  if (isError || !deal) {
    return (
      <div>
        {error instanceof Error ? error.message : "Ошибка загрузки проекта"}
      </div>
    );
  }

  return <DealPage deal={deal} />;
}

// ─────────────────────────────────────────────────────────────
// Route Guards
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

function RequireAdminOrSuperadmin({
  children,
}: {
  children: React.ReactElement;
}) {
  const { userId, globalRole } = useAuth();
  if (!userId) return <Navigate to="/login" replace />;
  if (globalRole !== "superadmin" && globalRole !== "tenant_admin") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

// ─────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────

function App() {
  return (
    <ContactModalProvider>
      <div className="min-h-screen w-full bg-[var(--bg-base)]">
        <ScrollToAnchor />

        <Routes>
          {/* ── Marketing ──────────────────────────────────── */}
          <Route path="/" element={<HomePage />} />
          <Route path="/capabilities" element={<CapabilitiesPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route
            path="/solutions/ma-due-diligence"
            element={<MaDueDiligencePage />}
          />
          <Route
            path="/solutions/contract-review"
            element={<ContractReviewPage />}
          />
          <Route
            path="/solutions/compliance"
            element={<CompliancePage />}
          />
          <Route
            path="/solutions/internal-audit"
            element={<InternalAuditPage />}
          />
          <Route path="/solutions/law-firms" element={<LawFirmsPage />} />
          <Route
            path="/solutions/corporate-legal"
            element={<CorporateLegalPage />}
          />
          <Route
            path="/solutions/audit-compliance"
            element={<AuditCompliancePage />}
          />
          <Route
            path="/solutions/counterparties"
            element={<CounterpartiesPage />}
          />
          <Route
            path="/solutions/real-estate"
            element={<RealEstatePage />}
          />

          {/* ── Auth ───────────────────────────────────────── */}
          <Route path="/login" element={<LoginPage />} />

          {/* ── Dashboard & Projects ───────────────────────── */}
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
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <NewProjectPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
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

          {/* ── Deal-level Instructions ─────────────────────── */}
          <Route
            path="/projects/:dealId/instructions"
            element={
              <RequireAuth>
                <AppShell>
                  <ProjectRouteGuard requiredCapability="canManageRequests">
                    <DealInstructionsPage />
                  </ProjectRouteGuard>
                </AppShell>
              </RequireAuth>
            }
          />

          <Route
            path="/projects/:dealId/instructions/overrides"
            element={
              <RequireAuth>
                <AppShell>
                  <ProjectRouteGuard requiredCapability="canManageRequests">
                    <DealOverridesPage />
                  </ProjectRouteGuard>
                </AppShell>
              </RequireAuth>
            }
          />

          <Route
            path="/projects/:dealId/instructions/overrides/:docType"
            element={
              <RequireAuth>
                <AppShell>
                  <ProjectRouteGuard requiredCapability="canManageRequests">
                    <DealOverrideDetailPage />
                  </ProjectRouteGuard>
                </AppShell>
              </RequireAuth>
            }
          />

          {/* ── Admin — Model Configs & Playbook Versions ───── */}
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

          {/* ── Admin — Instructions index ──────────────────── */}
          <Route
            path="/admin/instructions"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <InstructionsIndexPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          {/* ── Admin — Global Playbooks ────────────────────── */}
          <Route
            path="/admin/instructions/global-playbooks"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <GlobalPlaybooksPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/global-playbooks/:playbookId"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <GlobalPlaybookDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/global-playbooks/:playbookId/versions/:versionId"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <PlaybookVersionDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          {/* ── Admin — Global Instructions lifecycle ───────── */}
          <Route
            path="/admin/instructions/global-checks"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <GlobalInstructionsPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/global-checks/:instructionCode"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <GlobalInstructionDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/global-checks/:instructionCode/versions/:versionId"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <GlobalInstructionVersionDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          {/* ── Admin — Doc-Type Instructions ───────────────── */}
          <Route
            path="/admin/instructions/doc-types"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <DocTypeInstructionsPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/doc-types/:docType"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <DocTypeDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/instructions/doc-types/:docType/versions/:versionId"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <DocTypeVersionDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          {/* ── Tenant Admin ────────────────────────────────── */}
          <Route
            path="/tenant-admin"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantAdminPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          {/* ── Tenant-level Instructions ───────────────────── */}
          <Route
            path="/tenant-admin/instructions"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantInstructionsPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/overrides"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantOverridesPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/overrides/:docType"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantOverrideDetailPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          {/* ── Admin — Tenants ─────────────────────────────── */}
          <Route
            path="/admin"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <AdminPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/tenants/new"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <AdminTenantNewPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/tenants/:tenantId"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <AdminTenantDetailPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ContactModalProvider>
  );
}

export default App;


