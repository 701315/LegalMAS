// =============================================================
// src/pages/tenant-admin/tabs/UsersTab.tsx
//
// Вкладка "Пользователи" в admin panel. Отображает таблицу
// пользователей организации с expandable rows (показывающими
// проекты пользователя при expand).
//
// Design contract:
// - Empty state если users.length === 0
// - Sticky table header (top-0) с elevated-soft background
// - Table min-w-[820px] для readability на всех экранах
// - Scroll внутри tab (overflow-auto)
//
// State ownership:
// - expandedUserIds управляется in parent (main component),
//   потому что нужно управлять множественным expand через Set<string>
// - При переключении tabs состояние expanded сохраняется
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { TenantUserDTO } from "../../../api/tenantAdmin";
import { LABEL_XS } from "../constants";
import UserRow from "../components/UserRow";

export interface UsersTabProps {
  /** Массив пользователей для отображения */
  users: TenantUserDTO[];
  /** Set с ID развёрнутых пользователей */
  expandedUserIds: Set<string>;
  /** Callback для toggle expand/collapse конкретного пользователя */
  onToggleUser: (userId: string) => void;
  /** Callback при клике на project pill (открывает project drill down) */
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


