// =============================================================
// src/stores/uiStore.ts
// Zustand-хранилище для API-ключа, роли пользователя и проекта.
// =============================================================

import { create } from "zustand";
import type { UserRole } from "../types";
import type { ProjectRole } from "../api/auth";

export type GlobalRole =
  | "superadmin"
  | "tenant_admin"
  | "member";

interface UIState {
  apiKey: string | null;
  userRole: UserRole;

  setApiKey: (key: string | null) => void;
  setUserRole: (role: UserRole) => void;

  userId: string | null;
  userName: string | null;
  globalRole: GlobalRole | null;

  projectRoles: Record<string, ProjectRole>;

  setUserInfo: (data: {
    userId: string;
    userName: string;
    globalRole: GlobalRole;
    projectRoles: Record<string, ProjectRole>;
    apiKey?: string | null;
  }) => void;

  setProjectRole: (dealId: string, role: ProjectRole) => void;

  logout: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  apiKey: localStorage.getItem("mas_dd_api_key"),
  userRole:
    (localStorage.getItem("mas_dd_user_role") as UserRole) || "viewer",

  setApiKey: (key) => {
    if (key) {
      localStorage.setItem("mas_dd_api_key", key);
    } else {
      localStorage.removeItem("mas_dd_api_key");
    }
    set({ apiKey: key });
  },

  setUserRole: (role) => {
    localStorage.setItem("mas_dd_user_role", role);
    set({ userRole: role });
  },

  userId: localStorage.getItem("mas_dd_user_id"),
  userName: localStorage.getItem("mas_dd_user_name"),
  globalRole:
    (localStorage.getItem("mas_dd_global_role") as GlobalRole) || null,

  projectRoles: (() => {
    try {
      const raw = localStorage.getItem("mas_dd_project_roles");
      return raw ? (JSON.parse(raw) as Record<string, ProjectRole>) : {};
    } catch {
      return {};
    }
  })(),

  setUserInfo: ({ userId, userName, globalRole, projectRoles, apiKey }) => {
    localStorage.setItem("mas_dd_user_id", userId);
    localStorage.setItem("mas_dd_user_name", userName);
    localStorage.setItem("mas_dd_global_role", globalRole);
    localStorage.setItem(
      "mas_dd_project_roles",
      JSON.stringify(projectRoles),
    );

    if (apiKey !== undefined) {
      if (apiKey) {
        localStorage.setItem("mas_dd_api_key", apiKey);
      } else {
        localStorage.removeItem("mas_dd_api_key");
      }
    }

    set({
      userId,
      userName,
      globalRole,
      projectRoles,
      apiKey: apiKey ?? null,
    });
  },

  setProjectRole: (dealId: string, role: ProjectRole) => {
    set((state) => {
      const updated = { ...state.projectRoles, [dealId]: role };
      localStorage.setItem("mas_dd_project_roles", JSON.stringify(updated));
      return { projectRoles: updated };
    });
  },

  logout: () => {
    [
      "mas_dd_api_key",
      "mas_dd_user_role",
      "mas_dd_user_id",
      "mas_dd_user_name",
      "mas_dd_global_role",
      "mas_dd_project_roles",
    ].forEach((key) => localStorage.removeItem(key));

    set({
      apiKey: null,
      userRole: "viewer",
      userId: null,
      userName: null,
      globalRole: null,
      projectRoles: {},
    });
  },
}));

