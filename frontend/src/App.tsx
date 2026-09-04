import React from "react";
import { Routes, Route, Navigate, Outlet, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

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

// ── App pages ──────────────────────────────────
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import DealPage from "./pages/DealPage";
import DealListPage from "./pages/DealListPage";
import NewProjectPage from "./pages/NewProjectPage";
import ProjectUploadPage from "./pages/ProjectUploadPage";
import ProjectMembersPage from "./pages/ProjectMembersPage";
import DealPlaybookSelectorPage from "./pages/DealPlaybookSelectorPage";
import RelaunchPage from "./pages/RelaunchPage";
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
  const { t } = useTranslation("common");
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

  if (isLoading) return <div>{t("loading")}</div>;

  if (isError || !deal) {
    return (
      <div>
        {error instanceof Error ? error.message : t("projectLoadError")}
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
// Shared authenticated AppShell layout
// ─────────────────────────────────────────────────────────────

function AuthenticatedAppShellLayout() {
  return (
    <RequireAuth>
      <AppShell>
        <Outlet />
      </AppShell>
    </RequireAuth>
  );
}

// ─────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────

function App() {
  return (
    <ContactModalProvider>
      {/* Wrapper is height-agnostic here — actual height contract is
          managed via CSS in index.css based on html.app-shell-mode class.
          
          - Marketing mode: wrapper grows to content (min-h-screen from CSS)
          - App-shell mode: wrapper = height 100% (from CSS), completing
            the viewport-locked chain html → body → #root → wrapper → AppShell
          
          This class-based approach is the industry standard for SPAs that
          host both marketing pages and app-shell UI in one bundle. */}
      <div className="w-full bg-[var(--bg-base)]" data-app-root>
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

          {/* ── Legacy redirects — сохраняем вне общего shell ─ */}
          <Route
            path="/admin/playbook-versions"
            element={
              <Navigate
                to="/admin/instructions/playbooks-registry"
                replace
              />
            }
          />
          <Route
            path="/admin/instructions/playbook-versions"
            element={
              <Navigate
                to="/admin/instructions/playbooks-registry"
                replace
              />
            }
          />
          <Route
            path="/tenant-admin/instructions/playbook-versions"
            element={
              <Navigate
                to="/admin/instructions/playbooks-registry"
                replace
              />
            }
          />

          {/* ── Shared authenticated app shell ─────────────── */}
          <Route element={<AuthenticatedAppShellLayout />}>
            {/* ── Dashboard & base project routes ─────────── */}
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/deals" element={<DealListPage />} />
            <Route path="/projects/:dealId" element={<DealRouteWrapper />} />

            <Route
              path="/projects/:dealId/upload"
              element={
                <ProjectRouteGuard requiredCapability="canUploadDocuments">
                  <ProjectUploadPage />
                </ProjectRouteGuard>
              }
            />

            <Route
              path="/projects/:dealId/members"
              element={
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <ProjectMembersPage />
                </ProjectRouteGuard>
              }
            />

            <Route
              path="/projects/:dealId/playbooks/admin"
              element={
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <AdminPlaybookLinesPage />
                </ProjectRouteGuard>
              }
            />

            {/* ── Deal-level Instructions ─────────────────── */}
            <Route
              path="/projects/:dealId/instructions"
              element={
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <DealInstructionsPage />
                </ProjectRouteGuard>
              }
            />

            <Route
              path="/projects/:dealId/instructions/overrides"
              element={
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <DealOverridesPage />
                </ProjectRouteGuard>
              }
            />

            <Route
              path="/projects/:dealId/instructions/overrides/:docType"
              element={
                <ProjectRouteGuard requiredCapability="canManageRequests">
                  <DealOverrideDetailPage />
                </ProjectRouteGuard>
              }
            />

            {/* ── Admin or Superadmin routes ──────────────── */}
            <Route
              element={
                <RequireAdminOrSuperadmin>
                  <Outlet />
                </RequireAdminOrSuperadmin>
              }
            >
              <Route path="/projects/new" element={<NewProjectPage />} />

              <Route
                path="/projects/:dealId/playbook"
                element={
                  <ProjectRouteGuard requiredCapability="canManageRequests">
                    <DealPlaybookSelectorPage />
                  </ProjectRouteGuard>
                }
              />

              <Route
                path="/projects/:dealId/relaunch"
                element={
                  <ProjectRouteGuard requiredCapability="canStartRun">
                    <RelaunchPage />
                  </ProjectRouteGuard>
                }
              />

              <Route
                path="/admin/model-configs"
                element={<ModelConfigsAdminPage />}
              />

              {/* ── Tenant Admin ─────────────────────────── */}
              <Route path="/tenant-admin" element={<TenantAdminPage />} />

              {/* ── Tenant-level Instructions ────────────── */}
              <Route
                path="/tenant-admin/instructions"
                element={<TenantInstructionsPage />}
              />

              <Route
                path="/tenant-admin/instructions/playbook-studio"
                element={<TenantBasePlaybooksPage />}
              />

              <Route
                path="/tenant-admin/instructions/base-playbooks"
                element={<TenantBasePlaybooksPage />}
              />

              <Route
                path="/tenant-admin/instructions/base-global-checks"
                element={<TenantBaseGlobalChecksPage />}
              />

              <Route
                path="/tenant-admin/instructions/base-global-checks/:instructionCode"
                element={<TenantBaseGlobalCheckDetailPage />}
              />

              <Route
                path="/tenant-admin/instructions/base-doc-types"
                element={<TenantBaseDocTypesPage />}
              />

              <Route
                path="/tenant-admin/instructions/base-doc-types/:docType"
                element={<TenantBaseDocTypeDetailPage />}
              />

              <Route
                path="/tenant-admin/instructions/my-playbooks"
                element={<TenantOwnedPlaybooksPage />}
              />

              <Route
                path="/tenant-admin/instructions/overrides"
                element={<TenantOverridesPage />}
              />

              <Route
                path="/tenant-admin/instructions/overrides/new"
                element={<TenantOverrideCreatePage />}
              />

              <Route
                path="/tenant-admin/instructions/overrides/:overrideId"
                element={<TenantOverrideDetailPage />}
              />
            </Route>

            {/* ── Superadmin routes ───────────────────────── */}
            <Route
              element={
                <RequireSuperadmin>
                  <Outlet />
                </RequireSuperadmin>
              }
            >
              {/* Реестр стандартных playbook — read-only + экспорт */}
              <Route
                path="/admin/instructions/playbooks-registry"
                element={<PlaybooksRegistryPage />}
              />

              {/* ── Admin — Instructions index ───────────── */}
              <Route
                path="/admin/instructions"
                element={<InstructionsIndexPage />}
              />

              {/* ── Admin — Global Playbooks ─────────────── */}
              <Route
                path="/admin/instructions/global-playbooks"
                element={<GlobalPlaybooksPage />}
              />

              <Route
                path="/admin/instructions/playbook-studio"
                element={<GlobalPlaybooksPage />}
              />

              <Route
                path="/admin/instructions/global-playbooks/:playbookId"
                element={<GlobalPlaybookDetailPage />}
              />

              <Route
                path="/admin/instructions/global-playbooks/:playbookId/versions/:versionId"
                element={<PlaybookVersionDetailPage />}
              />

              {/* ── Admin — Global Instructions lifecycle ─ */}
              <Route
                path="/admin/instructions/global-checks"
                element={<GlobalInstructionsPage />}
              />

              <Route
                path="/admin/instructions/global-checks/:instructionCode"
                element={<GlobalInstructionDetailPage />}
              />

              {/* ── Admin — Doc-Type Instructions ────────── */}
              <Route
                path="/admin/instructions/doc-types"
                element={<DocTypeInstructionsPage />}
              />

              <Route
                path="/admin/instructions/doc-types/:docType"
                element={<DocTypeDetailPage />}
              />

              {/* ── Admin — Tenants ─────────────────────── */}
              <Route path="/admin" element={<AdminPage />} />

              <Route
                path="/admin/tenants/new"
                element={<AdminTenantNewPage />}
              />

              <Route
                path="/admin/tenants/:tenantId"
                element={<AdminTenantDetailPage />}
              />

              <Route
                path="/admin/tenants/:tenantId/projects"
                element={<AdminTenantProjectsPage />}
              />

              <Route
                path="/admin/monitoring"
                element={<AdminMonitoringPage />}
              />
            </Route>
          </Route>

          {/*
            LEGACY маршрут.
            Оставлен вне общего shell для сохранения текущего поведения —
            без аудита самого экрана не меняем его layout-contract.
          */}
          <Route
            path="/admin/instructions/global-checks/:instructionCode/versions/:versionId"
            element={
              <RequireSuperadmin>
                <GlobalInstructionVersionDetailPage />
              </RequireSuperadmin>
            }
          />

          {/*
            Legacy redirect.
            Оставлен вне общего shell для сохранения текущего поведения.
          */}
          <Route
            path="/admin/instructions/doc-types/:docType/versions/:versionId"
            element={
              <RequireSuperadmin>
                <DocTypeVersionLegacyRedirect />
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


