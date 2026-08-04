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
import NewProjectLaunchFlowPage from "./pages/NewProjectLaunchFlowPage";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import AdminPlaybookLinesPage from "./pages/AdminPlaybookLinesPage";
import ModelConfigsAdminPage from "./pages/ModelConfigsAdminPage";
import PlaybooksRegistryPage from "./pages/PlaybooksRegistryPage";
import AdminPage from "./pages/AdminPage";
import TenantAdminPage from "./pages/TenantAdminPage";
import AdminTenantNewPage from "./pages/AdminTenantNewPage";
import AdminTenantDetailPage from "./pages/AdminTenantDetailPage";
import AdminMonitoringPage from "./pages/AdminMonitoringPage";
import AdminTenantProjectsPage from "./pages/AdminTenantProjectsPage";

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

// ── Instructions — tenant-level (tenant_admin) ────────────────
import TenantInstructionsPage from "./pages/tenant-instructions/TenantInstructionsPage";
import TenantOverridesPage from "./pages/tenant-instructions/TenantOverridesPage";
import TenantOverrideCreatePage from "./pages/tenant-instructions/TenantOverrideCreatePage";
import TenantOverrideDetailPage from "./pages/tenant-instructions/TenantOverrideDetailPage";
import TenantBasePlaybooksPage from "./pages/tenant-instructions/TenantBasePlaybooksPage";
import TenantBaseGlobalChecksPage from "./pages/tenant-instructions/TenantBaseGlobalChecksPage";
import TenantBaseGlobalCheckDetailPage from "./pages/tenant-instructions/TenantBaseGlobalCheckDetailPage";
import TenantBaseDocTypesPage from "./pages/tenant-instructions/TenantBaseDocTypesPage";
import TenantBaseDocTypeDetailPage from "./pages/tenant-instructions/TenantBaseDocTypeDetailPage";
import TenantOwnedPlaybooksPage from "./pages/tenant-instructions/TenantOwnedPlaybooksPage";

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

function DocTypeVersionLegacyRedirect() {
  const { docType, versionId } = useParams<{
    docType: string;
    versionId: string;
  }>();

  if (!docType) {
    return <Navigate to="/admin/instructions/doc-types" replace />;
  }

  // Старый /versions/new больше не используется как отдельная страница.
  // Безопасно отправляем пользователя на объединённый detail screen.
  if (!versionId || versionId === "new") {
    return <Navigate to={`/admin/instructions/doc-types/${docType}`} replace />;
  }

  return (
    <Navigate
      to={`/admin/instructions/doc-types/${docType}?version=${encodeURIComponent(versionId)}`}
      replace
    />
  );
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
            path="/projects/new-v2"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <NewProjectLaunchFlowPage />
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
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <ProjectRouteGuard requiredCapability="canManageRequests">
                    <DealPlaybookSelectorPage />
                  </ProjectRouteGuard>
                </AppShell>
              </RequireAdminOrSuperadmin>
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

          {/* Реестр стандартных playbook — read-only + экспорт */}
          <Route
            path="/admin/instructions/playbooks-registry"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <PlaybooksRegistryPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          {/* Legacy redirects — старые URL ведут на новую страницу */}
          <Route
            path="/admin/playbook-versions"
            element={<Navigate to="/admin/instructions/playbooks-registry" replace />}
          />
          <Route
            path="/admin/instructions/playbook-versions"
            element={<Navigate to="/admin/instructions/playbooks-registry" replace />}
          />
          <Route
            path="/tenant-admin/instructions/playbook-versions"
            element={<Navigate to="/admin/instructions/playbooks-registry" replace />}
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
            path="/admin/instructions/playbook-studio"
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

          {/* Главная страница инструкции — sidebar с версиями + редактор выбранной версии */}
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

          {/*
            LEGACY маршрут.
            Оставлен для обратной совместимости — все внешние ссылки
            вида /versions/:versionId редиректятся на новый ?version=<id>.
            Можно удалить через несколько релизов.
          */}
          <Route
            path="/admin/instructions/global-checks/:instructionCode/versions/:versionId"
            element={
              <RequireSuperadmin>
                <GlobalInstructionVersionDetailPage />
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
                <DocTypeVersionLegacyRedirect />
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
            path="/tenant-admin/instructions/playbook-studio"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBasePlaybooksPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/base-playbooks"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBasePlaybooksPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/base-global-checks"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBaseGlobalChecksPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/base-global-checks/:instructionCode"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBaseGlobalCheckDetailPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/base-doc-types"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBaseDocTypesPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/base-doc-types/:docType"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantBaseDocTypeDetailPage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/my-playbooks"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantOwnedPlaybooksPage />
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
            path="/tenant-admin/instructions/overrides/new"
            element={
              <RequireAdminOrSuperadmin>
                <AppShell>
                  <TenantOverrideCreatePage />
                </AppShell>
              </RequireAdminOrSuperadmin>
            }
          />

          <Route
            path="/tenant-admin/instructions/overrides/:overrideId"
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

          <Route
            path="/admin/tenants/:tenantId/projects"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <AdminTenantProjectsPage />
                </AppShell>
              </RequireSuperadmin>
            }
          />

          <Route
            path="/admin/monitoring"
            element={
              <RequireSuperadmin>
                <AppShell>
                  <AdminMonitoringPage />
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


