// =============================================================
// src/hooks/useAuth.ts
// Хук для получения API-ключа и роли пользователя.
// =============================================================

import { useUIStore } from "../stores/uiStore";

export function useAuth() {
  const apiKey = useUIStore((s) => s.apiKey);
  const userRole = useUIStore((s) => s.userRole);
  const setApiKey = useUIStore((s) => s.setApiKey);
  const setUserRole = useUIStore((s) => s.setUserRole);

  return {
    apiKey,
    userRole,
    setApiKey,
    setUserRole,
  };
}
