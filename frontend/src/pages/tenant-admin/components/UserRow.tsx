// =============================================================
// src/pages/tenant-admin/components/UserRow.tsx
//
// Строка пользователя в таблице "Пользователи" admin panel.
// Отображает: имя/email, role badge, статус активности, кол-во
// проектов, дата создания. Expandable — при клике показывает
// список проектов пользователя.
//
// Design contract:
// - Кликабельная строка ТОЛЬКО если у пользователя есть проекты
//   (иначе expand не имеет смысла)
// - Chevron icon показывает состояние expand/collapse
// - Expanded state рендерит вторую <tr> с pills проектов
//
// State ownership:
// - expanded state поднят в parent (TenantAdminPage) — потому что
//   нужно управлять множественным expand (Set<string>)
// =============================================================

import React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { TenantUserDTO } from "../../../api/tenantAdmin";
import { ROLE_LABELS, FOCUS_RING } from "../constants";
import { formatDate, projectRoleLabel } from "../utils";

export interface UserRowProps {
  /** Пользователь для отображения */
  user: TenantUserDTO;
  /** Развёрнута ли строка (показываются проекты пользователя) */
  expanded: boolean;
  /** Callback для toggle expand/collapse */
  onToggle: () => void;
  /** Callback при клике на project pill */
  onOpenProject: (dealId: string) => void;
}

const UserRow: React.FC<UserRowProps> = ({
  user,
  expanded,
  onToggle,
  onOpenProject,
}) => {
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
              Активен
            </span>
          ) : (
            <span className="text-[10px] text-[var(--text-muted)]">
              Деактивирован
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {user.projects_count}
          </span>
        </td>
        <td className="px-4 py-3 text-[10px] text-[var(--text-muted)]">
          {formatDate(user.created_at)}
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


