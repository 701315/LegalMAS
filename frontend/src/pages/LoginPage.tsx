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
      setErrorText("Укажите логин и пароль.");
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
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#FAF8F5] px-4 text-[#1A1917]">
      <div className="w-full max-w-sm rounded-2xl border border-[#E8E4DD] bg-white px-6 py-7 shadow-sm">
        <div className="mb-6">
          <div className="inline-flex items-center rounded-full border border-[#E8E4DD] bg-[#F3F0EB] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#A8A29E]">
            Secure sign-in
          </div>

          <h1 className="mt-4 text-[20px] font-semibold tracking-tight text-[#1A1917]">
            Вход в Steloom
          </h1>
          <p className="mt-2 text-sm leading-6 text-[#78756F]">
            Используйте учётные данные, выданные администратором вашей команды.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="login"
              className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.14em] text-[#A8A29E]"
            >
              Логин
            </label>
            <input
              id="login"
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full rounded-xl border border-[#E8E4DD] bg-[#FAF8F5] px-3.5 py-2.5 text-sm text-[#1A1917] placeholder:text-[#A8A29E] outline-none transition-colors focus:border-[#C86B52] focus:bg-white"
              placeholder="Ваш логин"
              autoComplete="username"
              autoFocus
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-[12px] font-semibold uppercase tracking-[0.14em] text-[#A8A29E]"
            >
              Пароль
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-[#E8E4DD] bg-[#FAF8F5] px-3.5 py-2.5 text-sm text-[#1A1917] placeholder:text-[#A8A29E] outline-none transition-colors focus:border-[#C86B52] focus:bg-white"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {errorText && (
            <p className="rounded-xl border border-[#DC2626]/20 bg-[#FEE2E2] px-3.5 py-2.5 text-xs text-[#B91C1C]">
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
        className="mt-6 text-xs text-[#A8A29E] transition-colors hover:text-[#78756F]"
      >
        ← Вернуться на главную
      </button>
    </div>
  );
};

export default LoginPage;


