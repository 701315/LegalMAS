// =============================================================
// src/stores/uiStore.ts
// Zustand-хранилище для API-ключа, роли пользователя и проекта.
// =============================================================

import { create } from "zustand";
import type { UserRole } from "../types";

export type GlobalRole = "superadmin" | "user" | "system";
type ProjectRole = "admin" | "editor" | "viewer";

interface UIState {
  // Текущая логика (оставляем как есть для совместимости)
  apiKey: string | null;
  userRole: UserRole;

  setApiKey: (key: string | null) => void;
  setUserRole: (role: UserRole) => void;

  // Новые поля пользователя
  userId: string | null;
  userName: string | null;
  globalRole: GlobalRole | null;

  // Роли пользователя в проектах: deal_id → роль
  projectRoles: Record<string, ProjectRole>;

  // Установить всю информацию о пользователе одним вызовом
  setUserInfo: (data: {
    userId: string;
    userName: string;
    globalRole: GlobalRole;
    projectRoles: Record<string, ProjectRole>;
    apiKey?: string | null;
  }) => void;

  // Полный выход из системы
  logout: () => void;
}

/**
 * Хранилище UI-состояния:
 * - apiKey: хранится в localStorage (ключ mas_dd_api_key)
 * - userRole: хранится в localStorage (ключ mas_dd_user_role)
 * - userId, userName, globalRole, projectRoles: тоже в localStorage
 */
export const useUIStore = create<UIState>((set) => ({
  // --- старые поля ---
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

  // --- новые поля пользователя ---
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

  setUserInfo: ({
    userId,
    userName,
    globalRole,
    projectRoles,
    apiKey,
  }) => {
    // Сохраняем в localStorage
    localStorage.setItem("mas_dd_user_id", userId);
    localStorage.setItem("mas_dd_user_name", userName);
    localStorage.setItem("mas_dd_global_role", globalRole);
    localStorage.setItem(
      "mas_dd_project_roles",
      JSON.stringify(projectRoles),
    );

    // При необходимости обновляем apiKey (если он пришёл от бэкенда)
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

  logout: () => {
    // Удаляем все сохранённые поля из localStorage
    [
      "mas_dd_api_key",
      "mas_dd_user_role",
      "mas_dd_user_id",
      "mas_dd_user_name",
      "mas_dd_global_role",
      "mas_dd_project_roles",
    ].forEach((key) => localStorage.removeItem(key));

    // Сбрасываем состояние в дефолтное
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
