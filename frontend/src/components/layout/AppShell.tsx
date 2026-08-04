// src/components/layout/AppShell.tsx

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
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { useUserProjects } from "../../hooks/useUserProjects";
import Button from "../ui/Button";

const NAV_WIDTH_EXPANDED = 248;
const NAV_WIDTH_COLLAPSED = 64;
const MAX_PROJECTS_IN_SIDEBAR = 6;

const navItemBaseClassName =
  "group flex items-center gap-3 rounded-xl px-3 py-2 font-medium transition-all duration-150 " +
  "text-[length:var(--font-size-ui-sm)] leading-[var(--line-height-ui-sm)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]";

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
    className={({ isActive }) =>
      [
        navItemBaseClassName,
        "w-full",
        isActive
          ? "nav-item-active"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
        collapsed && "justify-center px-2",
      ]
        .filter(Boolean)
        .join(" ")
    }
  >
    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
    {!collapsed && <span className="truncate">{label}</span>}
  </NavLink>
);

const SidebarSectionLabel: React.FC<{
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
}> = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 px-1 py-1">
    <Icon className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden="true" />
    <span className="text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
      {label}
    </span>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Superadmin sidebar — три пункта администрирования системы
// ─────────────────────────────────────────────────────────────

interface SuperadminNavProps {
  collapsed: boolean;
}

const SuperadminNav: React.FC<SuperadminNavProps> = ({ collapsed }) => (
  <div className="mt-4 space-y-1">
    {!collapsed && (
      <SidebarSectionLabel icon={Settings} label="Администрирование" />
    )}
    <NavItem
      collapsed={collapsed}
      to="/admin"
      end
      label="Клиенты"
      icon={Building2}
    />
    <NavItem
      collapsed={collapsed}
      to="/admin/instructions"
      label="Инструкции"
      icon={BookOpen}
    />
    <NavItem
      collapsed={collapsed}
      to="/admin/monitoring"
      label="Мониторинг"
      icon={BarChart2}
    />
  </div>
);

// ─────────────────────────────────────────────────────────────
// Tenant admin sidebar
// ─────────────────────────────────────────────────────────────

interface TenantAdminNavProps {
  collapsed: boolean;
}

const TenantAdminNav: React.FC<TenantAdminNavProps> = ({ collapsed }) => (
  <div className="mt-4 space-y-1">
    {!collapsed && <SidebarSectionLabel icon={Settings} label="Организация" />}
    <NavItem
      collapsed={collapsed}
      to="/tenant-admin"
      end
      label="Панель администратора"
      icon={Settings}
    />
    <NavItem
      collapsed={collapsed}
      to="/tenant-admin/instructions"
      label="Инструкции"
      icon={BookOpen}
    />
  </div>
);

// ─────────────────────────────────────────────────────────────
// AppShell
// ─────────────────────────────────────────────────────────────

const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { globalRole, userId } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = React.useState(false);
  const [isLogoutOpen, setIsLogoutOpen] = React.useState(false);

  const navWidth = collapsed ? NAV_WIDTH_COLLAPSED : NAV_WIDTH_EXPANDED;

  const isSuperadmin = globalRole === "superadmin";
  const isTenantAdmin = globalRole === "tenant_admin";

  // Только tenant_admin и member создают/видят проекты в sidebar.
  // Superadmin управляет системой, проекты — не его рабочий контекст.
  const showProjectsSection = !isSuperadmin;
  const canCreateProject = isTenantAdmin;

  const { data: projectsData } = useUserProjects(userId);

  const sidebarProjects = showProjectsSection
    ? (projectsData ?? []).slice(0, MAX_PROJECTS_IN_SIDEBAR)
    : [];

  const hiddenProjectsCount = showProjectsSection
    ? Math.max(0, (projectsData?.length ?? 0) - MAX_PROJECTS_IN_SIDEBAR)
    : 0;

  const handleToggleSidebar = () => setCollapsed((v) => !v);

  const handleOpenLogout = () => setIsLogoutOpen(true);
  const handleCloseLogout = () => setIsLogoutOpen(false);
  const handleConfirmLogout = () => {
    setIsLogoutOpen(false);
    navigate("/login");
  };

  return (
    <div className="flex h-screen min-h-0 w-full overflow-hidden bg-[var(--bg-base)] text-[var(--text-primary)]">
      {/* ── Сайдбар ─────────────────────────────────────────── */}
      <aside
        className="relative flex h-full min-h-0 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-card)] transition-all duration-200"
        style={{ width: navWidth }}
        aria-label="Основная боковая навигация"
      >
        {/* Кнопка сворачивания */}
        <div className="absolute -right-3 top-4 z-20">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleToggleSidebar}
            aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
            aria-pressed={collapsed}
            className="h-7 min-h-0 w-7 rounded-full p-0 shadow-sm"
          >
            {collapsed ? (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </Button>
        </div>

        {/* Логотип */}
        <div className="flex shrink-0 items-center gap-3 px-4 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[var(--accent-primary)] text-xs font-semibold text-white shadow-sm">
            <span className="tracking-tight">S</span>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-[length:var(--font-size-body-sm)] leading-[var(--line-height-body-sm)] font-semibold tracking-tight text-[var(--text-primary)]">
                Steloom
              </div>
            </div>
          )}
        </div>

        {/* Навигация */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-3">
          <nav className="space-y-1" aria-label="Основная навигация">
            {/* ── Superadmin: только системное администрирование ── */}
            {isSuperadmin ? (
              <SuperadminNav collapsed={collapsed} />
            ) : (
              <>
                <NavItem
                  collapsed={collapsed}
                  to="/dashboard"
                  end
                  label="Dashboard"
                  icon={LayoutDashboard}
                />

                {/* Список проектов */}
                {!collapsed && showProjectsSection && (
                  <div className="mt-1 pl-2">
                    <SidebarSectionLabel
                      icon={BriefcaseBusiness}
                      label="Проекты"
                    />
                    <div className="mt-2 space-y-1">
                      {sidebarProjects.length > 0 ? (
                        sidebarProjects.map((project) => {
                          const isActive =
                            location.pathname ===
                              `/projects/${project.deal_id}` ||
                            location.pathname.startsWith(
                              `/projects/${project.deal_id}/`,
                            );

                          return (
                            <NavLink
                              key={project.deal_id}
                              to={`/projects/${project.deal_id}`}
                              className={({ isActive: linkActive }) =>
                                [
                                  "block rounded-xl border px-3 py-2 transition-all duration-150",
                                  "text-[length:var(--font-size-ui-sm)] leading-[var(--line-height-ui-sm)]",
                                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
                                  linkActive || isActive
                                    ? "border-[var(--accent-primary)]/20 bg-[var(--accent-muted)] text-[var(--text-primary)]"
                                    : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-subtle)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
                                ]
                                  .filter(Boolean)
                                  .join(" ")
                              }
                            >
                              <div className="truncate font-medium">
                                {project.deal_name}
                              </div>
                              <div className="mt-0.5 truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-[var(--text-muted)]">
                                {project.role}
                              </div>
                            </NavLink>
                          );
                        })
                      ) : (
                        <div className="rounded-xl border border-dashed border-[var(--border)] px-3 py-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-[var(--text-muted)]">
                          Нет доступных проектов
                        </div>
                      )}

                      {hiddenProjectsCount > 0 && (
                        <NavLink
                          to="/dashboard"
                          className="block rounded-xl px-3 py-2 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                        >
                          Ещё {hiddenProjectsCount}
                        </NavLink>
                      )}
                    </div>
                  </div>
                )}

                {/* Новый проект — только tenant_admin */}
                {canCreateProject && (
                  <div className="mt-4">
                    <NavItem
                      collapsed={collapsed}
                      to="/projects/new"
                      label="Новый проект"
                      icon={PlusSquare}
                    />
                  </div>
                )}

                {/* Tenant admin секция */}
                {isTenantAdmin && (
                  <TenantAdminNav collapsed={collapsed} />
                )}
              </>
            )}
          </nav>
        </div>

        {/* Профиль / выход */}
        <div className="shrink-0 border-t border-[var(--border)] px-3 py-3">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleOpenLogout}
            aria-label="Открыть окно выхода из профиля"
            fullWidth
            className={`h-auto rounded-xl bg-[var(--bg-elevated-soft)] px-3 py-2 text-left hover:bg-[var(--bg-card)] ${
              collapsed ? "justify-center" : "justify-start"
            }`}
            leftIcon={
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                aria-hidden="true"
              >
                <Users className="h-4 w-4" />
              </span>
            }
          >
            {!collapsed && (
              <span className="min-w-0">
                <span className="block truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold text-[var(--text-primary)]">
                  {globalRole ?? "user"}
                </span>
                <span className="block truncate text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-[var(--text-muted)]">
                  Выйти из профиля
                </span>
              </span>
            )}
          </Button>
        </div>
      </aside>

      {/* ── Рабочая область ─────────────────────────────────── */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-base)]">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--bg-card)] px-5">
          <div className="flex items-center gap-2">
            <span className="text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
              Review Workspace
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-1 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] text-[var(--color-success-text)]">
            <Shield className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Data secured</span>
          </div>
        </header>

        <div className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg-surface)] p-4 md:p-5">
          <div className="h-full min-h-0 min-w-0 overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-soft)] bg-[var(--bg-surface)]">
            {children}
          </div>
        </div>
      </main>

      {/* ── Диалог выхода ───────────────────────────────────── */}
      {isLogoutOpen && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/45 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="logout-dialog-title"
        >
          <div className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-2xl">
            <div className="mb-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
              ПОДТВЕРЖДЕНИЕ
            </div>
            <h2
              id="logout-dialog-title"
              className="text-base font-semibold text-[var(--text-primary)]"
            >
              Выйти из профиля?
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Вы будете перенаправлены на страницу входа и текущая сессия будет
              завершена.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={handleCloseLogout}
              >
                Нет
              </Button>
              <Button
                variant="danger"
                size="sm"
                type="button"
                onClick={handleConfirmLogout}
              >
                Да
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AppShell;


