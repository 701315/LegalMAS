// =============================================================
// src/pages/tenant-admin/components/UserRow.tsx
//
// User row in the "Users" table of the admin panel.
// Displays: name/email, role badge, active status, project count,
// creation date. Expandable — clicking reveals user's projects list.
//
// Design contract:
// - Clickable row ONLY if user has projects
//   (otherwise expand has no meaning)
// - Chevron icon indicates expand/collapse state
// - Expanded state renders a second <tr> with project pills
//
// State ownership:
// - expanded state is lifted to parent (TenantAdminPage) — because
//   multiple expand states need to be managed (Set<string>)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { TenantUserDTO } from "../../../api/tenantAdmin";
import { ROLE_LABELS, FOCUS_RING } from "../constants";
import { formatDate, projectRoleLabel } from "../utils";

export interface UserRowProps {
  /** User to display */
  user: TenantUserDTO;
  /** Whether the row is expanded (showing user's projects) */
  expanded: boolean;
  /** Callback to toggle expand/collapse */
  onToggle: () => void;
  /** Callback when clicking a project pill */
  onOpenProject: (dealId: string) => void;
}

const UserRow: React.FC<UserRowProps> = ({
  user,
  expanded,
  onToggle,
  onOpenProject,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const hasProjects = user.projects_count > 0;

  return (
    <>
      <tr
        className={`border-b border-[var(--border-subtle)] transition-colors ${
          hasProjects ? "cursor-pointer hover:bg-[var(--bg-elevated-soft)]" : ""
        }`}
        onClick={() => {
          if (hasProjects) onToggle();
        }}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {hasProjects ? (
              expanded ? (
                <ChevronDown
                  size={14}
                  className="shrink-0 text-[var(--text-muted)]"
                />
              ) : (
                <ChevronRight
                  size={14}
                  className="shrink-0 text-[var(--text-muted)]"
                />
              )
            ) : (
              <span className="inline-block w-3.5 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {user.full_name || user.email}
              </p>
              {user.full_name && (
                <p className="truncate text-[10px] text-[var(--text-muted)]">
                  {user.email}
                </p>
              )}
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
            {ROLE_LABELS[user.system_role] ?? user.system_role}
          </span>
        </td>
        <td className="px-4 py-3">
          {user.is_active ? (
            <span className="inline-flex items-center gap-1.5 text-[10px] text-[var(--color-success-text)]">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
              {t("userRow.active")}
            </span>
          ) : (
            <span className="text-[10px] text-[var(--text-muted)]">
              {t("userRow.deactivated")}
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {user.projects_count}
          </span>
        </td>
        <td className="px-4 py-3 text-[10px] text-[var(--text-muted)]">
          {formatDate(user.created_at, i18n.language)}
        </td>
      </tr>

      {expanded && hasProjects && (
        <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
          <td colSpan={5} className="px-4 py-3">
            <div className="ml-6 flex flex-wrap gap-1.5">
              {user.projects.map((p) => (
                <button
                  key={p.deal_id}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenProject(p.deal_id);
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-2.5 py-1 text-[11px] text-[var(--text-primary)] transition hover:border-[var(--accent-primary)] hover:bg-[var(--accent-muted)] ${FOCUS_RING}`}
                >
                  <span className="font-medium">{p.deal_name}</span>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    · {projectRoleLabel(p.role)}
                  </span>
                </button>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

export default UserRow;


