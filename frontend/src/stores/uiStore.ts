// =============================================================
// src/stores/uiStore.ts
// Zustand-хранилище для API-ключа и роли пользователя.
// =============================================================

import { create } from "zustand";
import type { UserRole } from "../types";

interface UIState {
  apiKey: string | null;
  userRole: UserRole;
  setApiKey: (key: string | null) => void;
  setUserRole: (role: UserRole) => void;
}

/**
 * Хранилище UI-состояния:
 * - apiKey: хранится также в localStorage (ключ mas_dd_api_key)
 * - userRole: хранится в localStorage (ключ mas_dd_user_role)
 */
export const useUIStore = create<UIState>((set) => ({
  apiKey: localStorage.getItem("mas_dd_api_key"),
  userRole: (localStorage.getItem("mas_dd_user_role") as UserRole) || "viewer",

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
}));
