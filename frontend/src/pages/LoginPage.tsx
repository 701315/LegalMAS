// =============================================================
// src/pages/LoginPage.tsx
// Страница входа: логин + пароль, сохранение пользователя в uiStore.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useLogin } from "../api/auth";
import Button from "../components/ui/Button";
import type { GlobalRole } from "../stores/uiStore";
import type { ProjectRole } from "../api/auth";
import type { ApiError } from "../types";

// Все известные роли бэкенда → GlobalRole фронта
const ROLE_MAP: Record<string, GlobalRole> = {
  superadmin: "superadmin",
  tenant_admin: "tenant_admin",
  member: "member",
};

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { setUserInfo, logout } = useAuth();
  const loginMutation = useLogin();

  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    logout();

    if (!login.trim() || !password.trim()) {
      setErrorText("Укажите email и пароль.");
      return;
    }

    loginMutation.mutate(
      { username: login.trim(), password },
      {
        onSuccess: (data) => {
          const user = data.user;

          const globalRole: GlobalRole =
            ROLE_MAP[user.global_role] ?? "member";

          const projectRoles: Record<string, ProjectRole> = {};

          setUserInfo({
            userId: user.id,
            userName: user.email ?? user.id,
            tenantId: user.tenant_id,
            globalRole,
            projectRoles,
            apiKey: data.access_token,
          });

          // Роль-зависимый редирект после логина.
          // Superadmin управляет системой — его рабочий контекст = Клиенты.
          // Tenant admin и member работают с проектами — их контекст = Dashboard.
          const landingPath =
            globalRole === "superadmin" ? "/admin" : "/dashboard";

          navigate(landingPath, { replace: true });
        },
        onError: (err: unknown) => {
          const apiErr = err as
            | ApiError
            | (ApiError & { response?: { data?: ApiError } })
            | Error
            | { message?: string }
            | null
            | undefined;

          const detailFromResponse =
            (apiErr as { response?: { data?: ApiError } })?.response?.data
              ?.detail;

          const detail =
            (apiErr as ApiError)?.detail ??
            detailFromResponse ??
            (apiErr as Error)?.message ??
            (apiErr as { message?: string })?.message ??
            "Ошибка входа. Проверьте логин и пароль.";

          setErrorText(String(detail));
        },
      },
    );
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--bg-base)] px-4 text-[var(--text-primary)]">
      <div className="w-full max-w-sm rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] px-6 py-7 shadow-sm">
        <div className="mb-6">
          <div className="inline-flex items-center rounded-full border border-[var(--border-color)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Secure sign-in
          </div>

          <h1 className="mt-4 text-[20px] font-semibold tracking-tight text-[var(--text-primary)]">
            Вход в Steloom
          </h1>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Используйте учётные данные, выданные администратором вашей команды.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="login"
              className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]"
            >
              Email
            </label>
            <input
              id="login"
              type="email"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-base)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]"
              placeholder="name@company.com"
              autoComplete="username"
              autoFocus
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]"
            >
              Пароль
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-base)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {errorText && (
            <p className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3.5 py-2.5 text-xs text-[var(--color-error-text)]">
              {errorText}
            </p>
          )}

          <Button
            type="submit"
            variant="primary"
            size="sm"
            fullWidth
            isLoading={loginMutation.isPending}
          >
            Войти
          </Button>
        </form>
      </div>

      <button
        type="button"
        onClick={() => navigate("/")}
        className="mt-6 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
      >
        ← Вернуться на главную
      </button>
    </div>
  );
};

export default LoginPage;


