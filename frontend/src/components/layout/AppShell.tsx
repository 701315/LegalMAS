// =============================================================
// src/components/layout/AppShell.tsx
// Основной каркас приложения с сайдбаром.
// Вариант, где список проектов — визуальный подраздел Dashboard.
// =============================================================

import React from "react";
import {
  LayoutDashboard,
  Shield,
  PlusSquare,
  Users,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../hooks/useAuth";
import client from "../../api/client";
import type { ProjectRole } from "../../api/auth";

interface AppShellProps {
  children: React.ReactNode;
}

interface UserProjectNavItem {
  deal_id: string;
  deal_name: string;
  role: ProjectRole;
  created_at: string;
  contact_person?: string | null;
}

const NAV_WIDTH_EXPANDED = 248;
const NAV_WIDTH_COLLAPSED = 64;
const MAX_PROJECTS_IN_SIDEBAR = 6;

async function fetchUserProjects(userId: string): Promise<UserProjectNavItem[]> {
  const res = await client.get<UserProjectNavItem[]>(
    `/api/v1/user/${userId}/projects`,
  );
  return res.data;
}

const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { globalRole, userId } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = React.useState(false);

  // Раздел "Проекты" считается "логическим подразделом" Dashboard.
  // Авто-открытие: открыт, если мы находимся на dashboard или внутри проектов.
  const isInDashboardArea =
    location.pathname === "/dashboard" ||
    location.pathname.startsWith("/projects/");

  const [isProjectsOpen, setIsProjectsOpen] = React.useState<boolean>(true);

  React.useEffect(() => {
    // При смене маршрута поддерживаем логичный дефолт:
    // в "зоне" dashboard/projects блок проектов открыт.
    if (isInDashboardArea) {
      setIsProjectsOpen(true);
    }
  }, [isInDashboardArea]);

  const navWidth = collapsed ? NAV_WIDTH_COLLAPSED : NAV_WIDTH_EXPANDED;
  const isSuperadmin = globalRole === "superadmin";

  const { data: projectsData } = useQuery({
    queryKey: ["sidebar-user-projects", userId],
    queryFn: () => fetchUserProjects(userId!),
    enabled: !!userId,
    staleTime: 60_000,
  });

  const sidebarProjects = (projectsData ?? []).slice(0, MAX_PROJECTS_IN_SIDEBAR);
  const hiddenProjectsCount = Math.max(
    0,
    (projectsData?.length ?? 0) - MAX_PROJECTS_IN_SIDEBAR,
  );

  const handleToggleSidebar = () => setCollapsed((v) => !v);

  const handleDashboardClick = () => {
    navigate("/dashboard");
    // Логика: клик по Dashboard гарантированно раскрывает подраздел "Проекты".
    setIsProjectsOpen(true);
  };

  return (
    <div className="flex h-screen w-full bg-[var(--bg-base)] text-[var(--text-primary)]">
      {/* SIDEBAR */}
      <aside
        className="relative flex h-full flex-col border-r border-[var(--border)] bg-[var(--bg-card)] transition-all duration-200"
        style={{ width: navWidth }}
      >
        {/* Кнопка сворачивания */}
        <button
          type="button"
          onClick={handleToggleSidebar}
          className="absolute -right-3 top-4 z-20 flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)] shadow-sm transition-all duration-150 hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
          aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5" />
          )}
        </button>

        {/* Лого / бренд */}
        <div className="flex items-center gap-3 px-4 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[var(--accent-primary)] text-xs font-semibold text-white shadow-sm">
            <span className="tracking-tight">LM</span>
          </div>

          {!collapsed && (
            <div className="min-w-0">
              <div className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
                LegalMAS
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                Review Workspace
              </div>
            </div>
          )}
        </div>

        {/* Навигация */}
        <div className="flex-1 overflow-y-auto px-3 pb-3">
          {/* Верхняя навигация */}
          <nav className="space-y-1">
            {/* Dashboard с логикой подраздела "Проекты" */}
            <DashboardNavItem
              collapsed={collapsed}
              isActive={location.pathname === "/dashboard"}
              onClick={handleDashboardClick}
            />

            {/* Блок "Проекты" — визуально под Dashboard, как его подраздел */}
            {!collapsed && isProjectsOpen && (
              <div className="mt-1 pl-2">
                <SidebarSectionLabel
                  icon={BriefcaseBusiness}
                  label="Проекты"
                />
                <div className="mt-2 space-y-1">
                  {sidebarProjects.length > 0 ? (
                    sidebarProjects.map((project) => {
                      const isActive =
                        location.pathname === `/projects/${project.deal_id}` ||
                        location.pathname.startsWith(
                          `/projects/${project.deal_id}/`,
                        );

                      return (
                        <NavLink
                          key={project.deal_id}
                          to={`/projects/${project.deal_id}`}
                          className={({ isActive: linkActive }) =>
                            [
                              "block rounded-xl border px-3 py-2 text-[12px] transition-all duration-150",
                              linkActive || isActive
                                ? "border-[var(--accent-primary)]/20 bg-[var(--accent-muted)] text-[var(--text-primary)]"
                                : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-soft)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
                            ]
                              .filter(Boolean)
                              .join(" ")
                          }
                        >
                          <div className="truncate font-medium">
                            {project.deal_name}
                          </div>
                          <div className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                            {project.role}
                          </div>
                        </NavLink>
                      );
                    })
                  ) : (
                    <div className="rounded-xl border border-dashed border-[var(--border)] px-3 py-3 text-[11px] text-[var(--text-muted)]">
                      Нет доступных проектов
                    </div>
                  )}

                  {hiddenProjectsCount > 0 && (
                    <NavLink
                      to="/dashboard"
                      className="block rounded-xl px-3 py-2 text-[11px] font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
                    >
                      Ещё {hiddenProjectsCount}
                    </NavLink>
                  )}
                </div>
              </div>
            )}

            {/* "Новый проект" — отдельным блоком ниже списка проектов */}
            {isSuperadmin && (
              <div className="mt-4">
                <NavItem
                  collapsed={collapsed}
                  to="/projects/new"
                  label="Новый проект"
                  icon={PlusSquare}
                />
              </div>
            )}
          </nav>
        </div>

        {/* Нижний блок с ролью / workspace */}
        <div className="border-t border-[var(--border)] px-3 py-3">
          <div
            className={`flex items-center ${collapsed ? "justify-center" : "gap-3"} rounded-xl bg-[var(--bg-elevated-soft)] px-3 py-2`}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-muted)] text-[var(--accent-primary)]">
              <Users className="h-4 w-4" />
            </div>

            {!collapsed && (
              <div className="min-w-0">
                <div className="text-[11px] font-semibold text-[var(--text-primary)]">
                  {globalRole ?? "user"}
                </div>
                <div className="text-[10px] text-[var(--text-muted)]">
                  LegalMAS workspace
                </div>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* MAIN AREA */}
      <main className="flex min-w-0 flex-1 flex-col bg-[var(--bg-base)]">
        {/* Верхний хедер */}
        <header className="flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--bg-card)] px-5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
              LegalMAS · Review Workspace
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-[11px] text-emerald-700">
            <Shield className="h-3.5 w-3.5" />
            <span>Data secured</span>
          </div>
        </header>

        {/* Контент */}
        <div className="flex-1 overflow-auto bg-[var(--bg-base)]">
          <div className="h-full w-full animate-fadein px-4 py-4 md:px-6 md:py-5">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
};

// =============================================================
// Компоненты навигации
// =============================================================

interface NavItemProps {
  to: string;
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  collapsed: boolean;
}

const NavItem: React.FC<NavItemProps> = ({
  to,
  label,
  icon: Icon,
  collapsed,
}) => (
  <NavLink
    to={to}
    className={({ isActive }) =>
      [
        "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-150",
        isActive
          ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
        collapsed && "justify-center px-2",
      ]
        .filter(Boolean)
        .join(" ")
    }
  >
    <Icon className="h-4 w-4 shrink-0" />
    {!collapsed && <span className="truncate">{label}</span>}
  </NavLink>
);

// Специальный NavItem для Dashboard, чтобы повесить onClick и логику подраздела.
interface DashboardNavItemProps {
  collapsed: boolean;
  isActive: boolean;
  onClick: () => void;
}

const DashboardNavItem: React.FC<DashboardNavItemProps> = ({
  collapsed,
  isActive,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition-all duration-150",
      isActive
        ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
        : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
      collapsed && "justify-center px-2",
    ]
      .filter(Boolean)
      .join(" ")}
  >
    <LayoutDashboard className="h-4 w-4 shrink-0" />
    {!collapsed && <span className="truncate">Dashboard</span>}
  </button>
);

// Заголовок секции в сайдбаре
const SidebarSectionLabel: React.FC<{
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
}> = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 px-1">
    <Icon className="h-3.5 w-3.5 text-[var(--text-muted)]" />
    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
      {label}
    </span>
  </div>
);

export default AppShell;


