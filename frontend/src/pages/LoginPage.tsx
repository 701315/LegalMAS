// =============================================================
// src/pages/LoginPage.tsx
// Страница входа: логин + пароль, сохранение пользователя в uiStore.
// Обновлено под общий дизайн workspace LegalMAS.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useLogin } from "../api/auth";
import Button from "../components/ui/Button";
import type { GlobalRole } from "../stores/uiStore";
import type { ProjectRole } from "../api/auth";
import type { ApiError } from "../types";

// Все известные роли бэкенда → GlobalRole фронта
const ROLE_MAP: Record<string, GlobalRole> = {
  superadmin: "superadmin",
  admin: "admin",
  editor: "editor",
  reviewer: "reviewer",
  viewer: "viewer",
  user: "user",
  system: "system",
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
      setErrorText("Укажите логин и пароль.");
      return;
    }

    loginMutation.mutate(
      { username: login.trim(), password },
      {
        onSuccess: (data) => {
          const user = data.user;

          const globalRole: GlobalRole =
            user.id === "admin"
              ? "superadmin"
              : ROLE_MAP[user.global_role] ?? "user";

          const projectRoles: Record<string, ProjectRole> = {};

          setUserInfo({
            userId: user.id,
            userName: user.email ?? user.id,
            globalRole,
            projectRoles,
            apiKey: data.access_token,
          });

          navigate("/dashboard", { replace: true });
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
      <button
        type="button"
        onClick={() => navigate("/")}
        className="group mb-8 flex items-center gap-3"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--accent-primary)] text-white shadow-sm">
          <Shield className="h-5 w-5" />
        </div>
        <div className="text-left">
          <p className="text-sm font-semibold leading-tight text-[var(--text-primary)]">
            LegalMAS
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            Платформа интеллектуального анализа правовых документов
          </p>
        </div>
      </button>

      <div className="w-full max-w-sm rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] px-6 py-7 shadow-sm">
        <div className="mb-6">
          <div className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Secure sign-in
          </div>

          <h1 className="mt-4 text-[20px] font-semibold tracking-tight text-[var(--text-primary)]">
            Вход в LegalMAS
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
              Логин
            </label>
            <input
              id="login"
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]"
              placeholder="Ваш логин"
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
              className="w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {errorText && (
            <p className="rounded-2xl border border-[color:rgba(161,53,68,0.22)] bg-[color:rgba(161,53,68,0.08)] px-3.5 py-2.5 text-xs text-[color:rgb(120,35,46)]">
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
        className="mt-6 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
      >
        ← Вернуться на главную
      </button>
    </div>
  );
};

export default LoginPage;




