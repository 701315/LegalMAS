// =============================================================
// src/hooks/useAuth.ts
// Хук для получения данных аутентификации и ролей пользователя.
// =============================================================

import { useUIStore } from "../stores/uiStore";

export function useAuth() {
  const apiKey = useUIStore((s) => s.apiKey);
  const userRole = useUIStore((s) => s.userRole);
  const setApiKey = useUIStore((s) => s.setApiKey);
  const setUserRole = useUIStore((s) => s.setUserRole);

  const userId = useUIStore((s) => s.userId);
  const userName = useUIStore((s) => s.userName);
  const tenantId = useUIStore((s) => s.tenantId);
  const globalRole = useUIStore((s) => s.globalRole);
  const projectRoles = useUIStore((s) => s.projectRoles);

  const setUserInfo = useUIStore((s) => s.setUserInfo);
  const logout = useUIStore((s) => s.logout);

  return {
    apiKey,
    userRole,
    setApiKey,
    setUserRole,
    userId,
    userName,
    tenantId,
    globalRole,
    projectRoles,
    setUserInfo,
    logout,
  };
}

