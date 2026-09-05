// frontend/src/components/layout/AppShell.tsx

import React from "react";
import {
  LayoutDashboard,
  Shield,
  PlusSquare,
  Users,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Settings,
  BookOpen,
  Building2,
  BarChart2,
  Menu,
  X,
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { LanguageSelector } from "../i18n/LanguageSelector";
import { useUserProjects } from "../../hooks/useUserProjects";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import Button from "../ui/Button";

const MAX_PROJECTS_IN_SIDEBAR = 6;
const DESKTOP_NAV_WIDTH_EXPANDED_CLASS = "lg:w-[248px] lg:min-w-[248px]";
const DESKTOP_NAV_WIDTH_COLLAPSED_CLASS = "lg:w-[80px] lg:min-w-[80px]";
const MOBILE_DRAWER_WIDTH_CLASS = "w-[248px] max-w-[85vw]";

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

const navItemBaseClassName =
  "group flex items-center gap-3 rounded-xl px-3 py-2.5 font-medium transition-all duration-150 " +
  "text-[length:var(--font-size-ui-sm)] leading-[var(--line-height-ui-sm)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900";

interface AppShellProps {
  children: React.ReactNode;
}

interface NavItemProps {
  to: string;
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  collapsed: boolean;
  end?: boolean;
}

type SidebarProject = {
  deal_id: string;
  deal_name: string;
  role: string;
  needs_setup?: boolean;
  analysis_completed?: boolean;
  is_processing?: boolean;
};

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) {
    return [];
  }

  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter(
    (element) =>
      !element.hasAttribute("disabled") &&
      element.tabIndex !== -1 &&
      element.getAttribute("aria-hidden") !== "true",
  );
}

function trapFocusWithin(
  event: React.KeyboardEvent<HTMLElement>,
  container: HTMLElement | null,
) {
  if (event.key !== "Tab") {
    return;
  }

  const focusableElements = getFocusableElements(container);

  if (focusableElements.length === 0) {
    event.preventDefault();
    return;
  }

  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];
  const activeElement = document.activeElement;

  if (event.shiftKey) {
    if (activeElement === firstElement || !container?.contains(activeElement)) {
      event.preventDefault();
      lastElement.focus();
    }

    return;
  }

  if (activeElement === lastElement) {
    event.preventDefault();
    firstElement.focus();
  }
}

const NavItem: React.FC<NavItemProps> = ({
  to,
  label,
  icon: Icon,
  collapsed,
  end = false,
}) => (
  <NavLink
    to={to}
    end={end}
    title={collapsed ? label : undefined}
    aria-label={collapsed ? label : undefined}
    className={({ isActive }) =>
      [
        navItemBaseClassName,
        "w-full border",
        isActive
          ? "bg-white/15 text-white shadow-sm backdrop-blur-md border-white/20 font-semibold"
          : "border-transparent text-slate-300 hover:bg-white/10 hover:border-white/10 hover:text-white",
        collapsed && "justify-center px-2",
      ]
        .filter(Boolean)
        .join(" ")
    }
  >
    <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
    {!collapsed && <span className="truncate">{label}</span>}
  </NavLink>
);

const SidebarSectionLabel: React.FC<{
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
}> = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 px-1 py-1">
    <Icon className="h-3.5 w-3.5 text-white/50" aria-hidden="true" />
    <span className="text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-white/50">
      {label}
    </span>
  </div>
);

interface SuperadminNavProps {
  collapsed: boolean;
}

const SuperadminNav: React.FC<SuperadminNavProps> = ({ collapsed }) => {
  const { t } = useTranslation("navigation");
  return (
    <div className="space-y-1">
      {!collapsed && (
        <SidebarSectionLabel icon={Settings} label={t("sidebar.adminSection")} />
      )}
      <NavItem
        collapsed={collapsed}
        to="/admin"
        end
        label={t("sidebar.clients")}
        icon={Building2}
      />
      <NavItem
        collapsed={collapsed}
        to="/admin/instructions"
        label={t("sidebar.instructions")}
        icon={BookOpen}
      />
      <NavItem
        collapsed={collapsed}
        to="/admin/monitoring"
        label={t("sidebar.monitoring")}
        icon={BarChart2}
      />
    </div>
  );
};

interface TenantAdminNavProps {
  collapsed: boolean;
}

const TenantAdminNav: React.FC<TenantAdminNavProps> = ({ collapsed }) => {
  const { t } = useTranslation("navigation");
  return (
    <div className="space-y-1">
      {!collapsed && <SidebarSectionLabel icon={Settings} label={t("sidebar.orgSection")} />}
      <NavItem
        collapsed={collapsed}
        to="/tenant-admin"
        end
        label={t("sidebar.adminPanel")}
        icon={Settings}
      />
      <NavItem
        collapsed={collapsed}
        to="/tenant-admin/instructions"
        label={t("sidebar.instructions")}
        icon={BookOpen}
      />
    </div>
  );
};

interface SidebarContentProps {
  collapsed: boolean;
  isMobile: boolean;
  currentPath: string;
  globalRole: string | null | undefined;
  isSuperadmin: boolean;
  isTenantAdmin: boolean;
  showProjectsSection: boolean;
  canCreateProject: boolean;
  sidebarProjects: SidebarProject[];
  hiddenProjectsCount: number;
  isProjectsLoading: boolean;
  isProjectsError: boolean;
  mobileCloseButtonRef?: React.RefObject<HTMLButtonElement | null>;
  onRequestCloseMobile?: () => void;
  onToggleSidebar?: () => void;
  onOpenLogout: () => void;
}

const SidebarContent: React.FC<SidebarContentProps> = ({
  collapsed,
  isMobile,
  currentPath,
  isSuperadmin,
  isTenantAdmin,
  showProjectsSection,
  canCreateProject,
  sidebarProjects,
  hiddenProjectsCount,
  isProjectsLoading,
  isProjectsError,
  mobileCloseButtonRef,
  onRequestCloseMobile,
  onToggleSidebar,
  onOpenLogout,
}) => {
  const { t } = useTranslation(["navigation", "admin"]);
  const { globalRole } = useAuth();

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      {!isMobile && onToggleSidebar && (
        <div className="absolute -right-5 top-4 z-20">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onToggleSidebar}
            aria-label={collapsed ? t("actions.expandMenu") : t("actions.collapseMenu")}
            aria-pressed={collapsed}
            className="flex h-10 min-h-0 w-10 items-center justify-center rounded-full border border-slate-200 bg-white p-0 text-slate-700 shadow-md transition hover:bg-slate-50 hover:text-slate-900 focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        </div>
      )}

      <div className="flex shrink-0 items-center gap-3 px-4 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[var(--accent-primary)] text-xs font-semibold text-white shadow-sm">
          <span className="tracking-tight">S</span>
        </div>

        {!collapsed && (
          <div className="min-w-0">
            <div className="text-[length:var(--font-size-body-sm)] leading-[var(--line-height-body-sm)] font-semibold tracking-tight text-white">
              Steloom
            </div>
          </div>
        )}

        {isMobile && (
          <button
            ref={mobileCloseButtonRef}
            type="button"
            onClick={onRequestCloseMobile}
            aria-label={t("actions.closeMenu")}
            className="ml-auto inline-flex h-11 w-11 items-center justify-center rounded-xl text-white/50 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-3 pb-3">
        <nav className="flex flex-1 flex-col" aria-label={t("actions.mainNav")}>
          {isSuperadmin ? (
            <div className="space-y-1">
              <SuperadminNav collapsed={collapsed} />
            </div>
          ) : (
            <>
              {/* Upper Section */}
              <div className="space-y-1">
                <NavItem
                  collapsed={collapsed}
                  to="/dashboard"
                  end
                  label={t("sidebar.dashboard")}
                  icon={LayoutDashboard}
                />

                {!collapsed && showProjectsSection && (
                  <div className="mt-2 pl-2">
                    <SidebarSectionLabel
                      icon={BriefcaseBusiness}
                      label={t("sidebar.projects")}
                    />
                    <div className="mt-2 space-y-1">
                      {isProjectsLoading ? (
                        Array.from({ length: 3 }).map((_, index) => (
                          <div
                            key={index}
                            className="rounded-xl border border-transparent px-3 py-2"
                          >
                            <div className="h-4 w-3/4 animate-pulse rounded bg-white/10" />
                            <div className="mt-1.5 h-3 w-1/2 animate-pulse rounded bg-white/5" />
                          </div>
                        ))
                      ) : isProjectsError ? (
                        <div className="rounded-xl border border-dashed border-white/20 px-3 py-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-white/50">
                          {t("sidebar.loadError")}
                        </div>
                      ) : sidebarProjects.length > 0 ? (
                        sidebarProjects.map((project) => {
                          const isActive =
                            currentPath === `/projects/${project.deal_id}` ||
                            currentPath.startsWith(`/projects/${project.deal_id}/`);

                          return (
                            <NavLink
                              key={project.deal_id}
                              to={`/projects/${project.deal_id}`}
                              className={() =>
                                [
                                  "block rounded-xl border px-3 py-2 transition-all duration-150",
                                  "text-[length:var(--font-size-ui-sm)] leading-[var(--line-height-ui-sm)]",
                                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900",
                                  isActive
                                    ? "bg-white/15 text-white shadow-sm backdrop-blur-md border-white/20 font-semibold"
                                    : "border-transparent text-slate-300 hover:border-white/10 hover:bg-white/10 hover:text-white",
                                ].join(" ")
                              }
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="truncate font-medium">
                                  {project.deal_name}
                                </div>

                                {project.needs_setup ? (
                                  <span
                                    className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-amber-200"
                                    title={t("sidebar.needsSetup")}
                                  >
                                    !
                                  </span>
                                ) : project.analysis_completed ? (
                                  <span
                                    className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-200"
                                    title={t("sidebar.analysisCompleted")}
                                  >
                                    ✓
                                  </span>
                                ) : project.is_processing ? (
                                  <span
                                    className="shrink-0 flex h-4 w-4 items-center justify-center"
                                    title={t("sidebar.analysisRunning")}
                                  >
                                    <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-white" />
                                  </span>
                                ) : null}
                              </div>
                            </NavLink>
                          );
                        })
                      ) : (
                        <div className="rounded-xl border border-dashed border-white/20 px-3 py-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-white/50">
                          {t("sidebar.noProjects")}
                        </div>
                      )}

                      {hiddenProjectsCount > 0 && (
                        <NavLink
                          to="/dashboard"
                          className="block rounded-xl px-3 py-2 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-medium text-slate-400 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
                        >
                          {t("sidebar.moreProjects", { count: hiddenProjectsCount })}
                        </NavLink>
                      )}
                    </div>
                  </div>
                )}

                {canCreateProject && (
                  <div className="mt-4">
                    <NavItem
                      collapsed={collapsed}
                      to="/projects/new"
                      label={t("sidebar.newProject")}
                      icon={PlusSquare}
                    />
                  </div>
                )}
              </div>

              {/* Bottom Section (Organization / Admin) */}
              {isTenantAdmin && (
                <div className="mt-auto pt-4 border-t border-white/15">
                  <TenantAdminNav collapsed={collapsed} />
                </div>
              )}
            </>
          )}
        </nav>
      </div>

      <div className="shrink-0 border-t border-white/15 px-3 py-3">
        <button
          type="button"
          onClick={onOpenLogout}
          aria-label={t("actions.logout")}
          className={[
            "flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 transition hover:bg-white/15 text-slate-300 hover:text-white",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900",
            collapsed ? "justify-center" : "justify-start text-left",
          ].join(" ")}
        >
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/10 text-white shadow-sm"
            aria-hidden="true"
          >
            <Users className="h-4 w-4" />
          </span>

          {!collapsed && (
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold text-white">
                {t(`projectMembers.systemRoles.${globalRole ?? "member"}`, { ns: "admin", defaultValue: globalRole ?? "User" })}
              </span>
              <span className="block truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-black">
                {t("actions.logout")}
              </span>
            </span>
          )}
        </button>
      </div>
    </div>
  );
};

const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { t } = useTranslation("navigation");
  const { globalRole, userId, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
  const [isLogoutOpen, setIsLogoutOpen] = React.useState(false);

  const hamburgerButtonRef = React.useRef<HTMLButtonElement>(null);
  const mobileCloseButtonRef = React.useRef<HTMLButtonElement>(null);
  const mobileDrawerRef = React.useRef<HTMLDivElement>(null);
  const logoutDialogRef = React.useRef<HTMLDivElement>(null);
  const logoutCancelButtonRef = React.useRef<HTMLButtonElement>(null);

  const restoreMobileFocusRef = React.useRef(false);
  const wasMobileNavOpenRef = React.useRef(false);
  const logoutReturnFocusRef = React.useRef<HTMLElement | null>(null);
  const wasLogoutOpenRef = React.useRef(false);

  React.useEffect(() => {
    document.documentElement.classList.add("app-shell-mode");
    return () => {
      document.documentElement.classList.remove("app-shell-mode");
    };
  }, []);

  const isSuperadmin = globalRole === "superadmin";
  const isTenantAdmin = globalRole === "tenant_admin";

  const showProjectsSection = !isSuperadmin;
  const canCreateProject = isTenantAdmin;

  const { data: projectsData, isLoading: isProjectsLoading, isError: isProjectsError } =
    useUserProjects(userId);

  const sidebarProjects: SidebarProject[] = showProjectsSection
    ? ((projectsData ?? []).slice(0, MAX_PROJECTS_IN_SIDEBAR) as SidebarProject[])
    : [];

  const hiddenProjectsCount = showProjectsSection
    ? Math.max(0, (projectsData?.length ?? 0) - MAX_PROJECTS_IN_SIDEBAR)
    : 0;

  const handleToggleSidebar = () => setCollapsed((value) => !value);

  const handleOpenMobileNav = () => {
    setMobileNavOpen(true);
  };

  const handleCloseMobileNav = (restoreFocus: boolean) => {
    restoreMobileFocusRef.current = restoreFocus;
    setMobileNavOpen(false);
  };

  const handleOpenLogout = () => {
    if (mobileNavOpen) {
      logoutReturnFocusRef.current = hamburgerButtonRef.current;
      handleCloseMobileNav(false);
    } else {
      logoutReturnFocusRef.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
    }

    setIsLogoutOpen(true);
  };

  const handleCloseLogout = () => {
    setIsLogoutOpen(false);
  };

  const handleConfirmLogout = () => {
    logoutReturnFocusRef.current = null;
    setIsLogoutOpen(false);
    logout();
    navigate("/login", { replace: true });
  };

  const handleMobileDrawerKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key === "Escape") {
      event.preventDefault();
      handleCloseMobileNav(true);
      return;
    }

    trapFocusWithin(event, mobileDrawerRef.current);
  };

  const handleLogoutDialogKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key === "Escape") {
      event.preventDefault();
      handleCloseLogout();
      return;
    }

    trapFocusWithin(event, logoutDialogRef.current);
  };

  React.useEffect(() => {
    if (isDesktop && mobileNavOpen) {
      handleCloseMobileNav(false);
    }
  }, [isDesktop, mobileNavOpen]);

  React.useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  React.useEffect(() => {
    if (!mobileNavOpen || isDesktop) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavOpen, isDesktop]);

  React.useEffect(() => {
    if (mobileNavOpen && !isDesktop) {
      wasMobileNavOpenRef.current = true;

      window.requestAnimationFrame(() => {
        mobileCloseButtonRef.current?.focus();
      });

      return;
    }

    if (wasMobileNavOpenRef.current) {
      if (restoreMobileFocusRef.current && !isDesktop) {
        window.requestAnimationFrame(() => {
          hamburgerButtonRef.current?.focus();
        });
      }

      restoreMobileFocusRef.current = false;
      wasMobileNavOpenRef.current = false;
    }
  }, [mobileNavOpen, isDesktop]);

  React.useEffect(() => {
    if (isLogoutOpen) {
      wasLogoutOpenRef.current = true;

      window.requestAnimationFrame(() => {
        logoutCancelButtonRef.current?.focus();
      });

      return;
    }

    if (wasLogoutOpenRef.current) {
      const focusTarget = logoutReturnFocusRef.current;

      logoutReturnFocusRef.current = null;
      wasLogoutOpenRef.current = false;

      if (focusTarget && document.contains(focusTarget)) {
        window.requestAnimationFrame(() => {
          focusTarget.focus();
        });
      }
    }
  }, [isLogoutOpen]);

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-[var(--bg-base)] text-[var(--text-primary)]">
      {/* ── Тёмный сайдбар на десктопе (позиционирование left top) ── */}
      <aside
        className={[
          "relative hidden h-full min-h-0 shrink-0 flex-col border-r border-white/15 transition-[width] duration-200 lg:flex",
          collapsed
            ? DESKTOP_NAV_WIDTH_COLLAPSED_CLASS
            : DESKTOP_NAV_WIDTH_EXPANDED_CLASS,
        ].join(" ")}
        aria-label={t("actions.mainNav")}
        style={{
          backgroundImage:
            "linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('/projectpicture.png')",
          backgroundSize: "cover",
          backgroundPosition: "left top",
          backgroundRepeat: "no-repeat",
        }}
      >
        <SidebarContent
          collapsed={collapsed}
          isMobile={false}
          currentPath={location.pathname}
          globalRole={globalRole}
          isSuperadmin={isSuperadmin}
          isTenantAdmin={isTenantAdmin}
          showProjectsSection={showProjectsSection}
          canCreateProject={canCreateProject}
          sidebarProjects={sidebarProjects}
          hiddenProjectsCount={hiddenProjectsCount}
          isProjectsLoading={isProjectsLoading}
          isProjectsError={isProjectsError}
          onToggleSidebar={handleToggleSidebar}
          onOpenLogout={handleOpenLogout}
        />
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-base)]">
        <header className="grid h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[var(--border)] bg-[var(--bg-card)] px-4 lg:px-5">
          <div className="flex items-center justify-start">
            {!isDesktop && (
              <button
                ref={hamburgerButtonRef}
                type="button"
                onClick={handleOpenMobileNav}
                aria-label={t("actions.openNav")}
                aria-expanded={mobileNavOpen}
                aria-controls="steloom-mobile-nav"
                className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
              >
                <Menu className="h-5 w-5" aria-hidden="true" />
              </button>
            )}
          </div>

          <span className="justify-self-center truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            {t("header.workspace")}
          </span>

          <div className="flex items-center justify-end gap-3">
            <LanguageSelector variant="minimal" />
            <div className="flex shrink-0 items-center gap-2 rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-1 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-[var(--color-success-text)]">
              <Shield className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{t("header.dataSecured")}</span>
            </div>
          </div>
        </header>

        <div className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg-surface)]">
          {children}
        </div>
      </main>

      {!isDesktop && mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            tabIndex={-1}
            aria-label={t("actions.closeMenu")}
            onClick={() => handleCloseMobileNav(true)}
            className="absolute inset-0 bg-black/45 backdrop-blur-[2px]"
          />

          <div
            ref={mobileDrawerRef}
            id="steloom-mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-labelledby="steloom-mobile-nav-title"
            onKeyDown={handleMobileDrawerKeyDown}
            className={`${MOBILE_DRAWER_WIDTH_CLASS} relative h-full border-r border-white/15 shadow-2xl`}
            style={{
              backgroundImage:
                "linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('/projectpicture.png')",
              backgroundSize: "cover",
              backgroundPosition: "left top",
              backgroundRepeat: "no-repeat",
            }}
          >
            <h2 id="steloom-mobile-nav-title" className="sr-only">
              {t("actions.mainNav")}
            </h2>

            <SidebarContent
              collapsed={false}
              isMobile={true}
              currentPath={location.pathname}
              globalRole={globalRole}
              isSuperadmin={isSuperadmin}
              isTenantAdmin={isTenantAdmin}
              showProjectsSection={showProjectsSection}
              canCreateProject={canCreateProject}
              sidebarProjects={sidebarProjects}
              hiddenProjectsCount={hiddenProjectsCount}
              isProjectsLoading={isProjectsLoading}
              isProjectsError={isProjectsError}
              mobileCloseButtonRef={mobileCloseButtonRef}
              onRequestCloseMobile={() => handleCloseMobileNav(true)}
              onOpenLogout={handleOpenLogout}
            />
          </div>
        </div>
      )}

      {isLogoutOpen && (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            tabIndex={-1}
            aria-label={t("actions.closeLogout")}
            onClick={handleCloseLogout}
            className="absolute inset-0 bg-black/45 backdrop-blur-[2px]"
          />

          <div className="relative z-10 flex min-h-full items-center justify-center p-4">
            <div
              ref={logoutDialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="logout-dialog-title"
              onKeyDown={handleLogoutDialogKeyDown}
              className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-2xl"
            >
              <div className="mb-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                {t("logout.heading")}
              </div>

              <h2
                id="logout-dialog-title"
                className="text-base font-semibold text-[var(--text-primary)]"
              >
                {t("logout.title")}
              </h2>

              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {t("logout.message")}
              </p>

              <div className="mt-5 flex justify-end gap-2">
                <Button
                  ref={logoutCancelButtonRef}
                  variant="secondary"
                  size="sm"
                  type="button"
                  onClick={handleCloseLogout}
                >
                  {t("logout.cancel")}
                </Button>

                <Button
                  variant="danger"
                  size="sm"
                  type="button"
                  onClick={handleConfirmLogout}
                >
                  {t("logout.confirm")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AppShell;


