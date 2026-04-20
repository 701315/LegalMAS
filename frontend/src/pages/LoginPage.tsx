// =============================================================
// src/pages/LoginPage.tsx
// Страница входа: логин + пароль, сохранение пользователя в uiStore.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useLogin } from "../api/auth";
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
            (apiErr as { response?: { data?: ApiError } })?.response?.data?.detail;

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
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 text-slate-900">
      {/* Логотип-ссылка на лендинг */}
      <button
        type="button"
        onClick={() => navigate("/")}
        className="group mb-8 flex items-center gap-2"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-indigo-700 shadow">
          <Shield className="h-5 w-5 text-white" />
        </div>
        <div className="text-left">
          <p className="text-base font-bold leading-none text-slate-900">
            LegalMAS
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Система интеллектуального анализа правовых документов
          </p>
        </div>
      </button>

      {/* Карточка формы */}
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 text-slate-900 shadow-sm">
        <h1 className="mb-1 text-lg font-bold text-slate-900">
          Вход в систему
        </h1>
        <p className="mb-6 text-sm text-slate-500">
          Введите логин и пароль, выданные администратором.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">
              Логин
            </label>
            <input
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 caret-slate-900 placeholder:text-slate-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Ваш логин"
              autoComplete="username"
              autoFocus
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">
              Пароль
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 caret-slate-900 placeholder:text-slate-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {errorText && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
              {errorText}
            </p>
          )}

          <button
            type="submit"
            disabled={loginMutation.isPending}
            className="mt-2 w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60"
          >
            {loginMutation.isPending ? "Входим…" : "Войти"}
          </button>
        </form>
      </div>

      {/* Ссылка назад */}
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mt-6 text-xs text-slate-500 transition-colors hover:text-slate-700"
      >
        ← Вернуться на главную
      </button>
    </div>
  );
};

export default LoginPage;


