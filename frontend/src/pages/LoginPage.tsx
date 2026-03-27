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

// Все известные роли бэкенда → GlobalRole фронта
const ROLE_MAP: Record<string, GlobalRole> = {
  superadmin: "superadmin",
  admin:      "admin",
  editor:     "editor",
  reviewer:   "reviewer",
  viewer:     "viewer",
  user:       "user",
  system:     "system",
};

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { setUserInfo, logout } = useAuth();
  const loginMutation = useLogin();

  const [login, setLogin]       = useState("");
  const [password, setPassword] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    logout(); // сбрасываем старое состояние

    if (!login || !password) {
      setErrorText("Укажите логин и пароль.");
      return;
    }

    loginMutation.mutate(
      { username: login, password },
      {
        onSuccess: (data) => {
          const user = data.user;

          // DEV: логин "admin" → superadmin
          // PROD: маппим через таблицу, неизвестные роли → "user"
          const globalRole: GlobalRole =
            user.id === "admin"
              ? "superadmin"
              : ROLE_MAP[user.global_role] ?? "user";

          const projectRoles: Record<string, ProjectRole> = {};

          setUserInfo({
            userId:       user.id,
            userName:     user.email ?? user.id,
            globalRole,
            projectRoles,
            apiKey:       data.access_token,
          });

          navigate("/dashboard");
        },
        onError: (err: any) => {
          const detail =
            err?.detail ||
            err?.message ||
            "Ошибка входа. Проверьте логин и пароль.";
          setErrorText(String(detail));
        },
      }
    );
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-4">

      {/* Логотип-ссылка на лендинг */}
      <button
        onClick={() => navigate("/")}
        className="flex items-center gap-2 mb-8 group"
      >
        <div className="w-9 h-9 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-lg flex items-center justify-center shadow">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div className="text-left">
          <p className="text-base font-bold text-slate-900 leading-none">LegalMAS</p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Система интеллектуального анализа правовых документов
          </p>
        </div>
      </button>

      {/* Карточка формы */}
      <div className="w-full max-w-sm bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        <h1 className="text-lg font-bold text-slate-900 mb-1">Вход в систему</h1>
        <p className="text-sm text-slate-500 mb-6">
          Введите логин и пароль, выданные администратором.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Логин
            </label>
            <input
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full px-3 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Ваш логин"
              autoComplete="username"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Пароль
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {errorText && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {errorText}
            </p>
          )}

          <button
            type="submit"
            disabled={loginMutation.isPending}
            className="w-full px-4 py-2.5 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 transition-colors mt-2"
          >
            {loginMutation.isPending ? "Входим…" : "Войти"}
          </button>
        </form>
      </div>

      {/* Ссылка назад */}
      <button
        onClick={() => navigate("/")}
        className="mt-6 text-xs text-slate-400 hover:text-slate-600 transition-colors"
      >
        ← Вернуться на главную
      </button>

    </div>
  );
};

export default LoginPage;
