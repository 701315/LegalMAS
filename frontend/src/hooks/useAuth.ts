// =============================================================
// src/hooks/useAuth.ts
// Хук для получения данных аутентификации и ролей пользователя.
// =============================================================

import { useUIStore } from "../stores/uiStore";

export function useAuth() {
  // Старые поля (для совместимости с существующим кодом)
  const apiKey = useUIStore((s) => s.apiKey);
  const userRole = useUIStore((s) => s.userRole);
  const setApiKey = useUIStore((s) => s.setApiKey);
  const setUserRole = useUIStore((s) => s.setUserRole);

  // Новые поля пользователя
  const userId = useUIStore((s) => s.userId);
  const userName = useUIStore((s) => s.userName);
  const globalRole = useUIStore((s) => s.globalRole);
  const projectRoles = useUIStore((s) => s.projectRoles);

  // Новые методы
  const setUserInfo = useUIStore((s) => s.setUserInfo);
  const logout = useUIStore((s) => s.logout);

  // ВРЕМЕННЫЙ dev-override:
  // если userId === "admin", считаем, что он admin во всех проектах.
  const overriddenProjectRoles =
    userId === "admin"
      ? new Proxy(projectRoles, {
          get(target, prop: string) {
            // если для конкретного dealId уже есть роль — используем её,
            // иначе по умолчанию считаем admin
            return (target as any)[prop] ?? "admin";
          },
        })
      : projectRoles;

  return {
    // старое API
    apiKey,
    userRole,
    setApiKey,
    setUserRole,

    // новое API
    userId,
    userName,
    globalRole,
    projectRoles: overriddenProjectRoles,
    setUserInfo,
    logout,
  };
}
