// =============================================================
// src/pages/tenant-admin/tabs/UsersTab.tsx
//
// "Users" tab in admin panel. Displays organization users table
// with expandable rows (showing user's projects on expand).
//
// Design contract:
// - Empty state if users.length === 0
// - Sticky table header (top-0) with elevated-soft background
// - Table min-w-[820px] for readability on all screens
// - Scroll inside tab (overflow-auto)
//
// State ownership:
// - expandedUserIds is managed in parent (main component),
//   because multiple expand states need to be controlled via Set<string>
// - Expanded state persists when switching tabs
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { TenantUserDTO } from "../../../api/tenantAdmin";
import { LABEL_XS } from "../constants";
import UserRow from "../components/UserRow";

export interface UsersTabProps {
  /** Array of users to display */
  users: TenantUserDTO[];
  /** Set of expanded user IDs */
  expandedUserIds: Set<string>;
  /** Callback to toggle expand/collapse for a specific user */
  onToggleUser: (userId: string) => void;
  /** Callback when clicking project pill (opens project drill down) */
  onOpenProject: (dealId: string) => void;
}

const UsersTab: React.FC<UsersTabProps> = ({
  users,
  expandedUserIds,
  onToggleUser,
  onOpenProject,
}) => {
  const { t } = useTranslation("tenantAdmin");

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      {users.length === 0 ? (
        <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">
          {t("usersTab.noUsers")}
        </div>
      ) : (
        <table className="w-full min-w-[820px] border-collapse">
          <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
            <tr className="border-b border-[var(--border)]">
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("usersTab.headers.user")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("usersTab.headers.role")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("usersTab.headers.status")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("usersTab.headers.projects")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("usersTab.headers.added")}
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                expanded={expandedUserIds.has(u.id)}
                onToggle={() => onToggleUser(u.id)}
                onOpenProject={onOpenProject}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default UsersTab;


