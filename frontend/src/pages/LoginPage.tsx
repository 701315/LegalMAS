// =============================================================
// src/pages/LoginPage.tsx
// Страница входа: логин + пароль, сохранение пользователя в uiStore.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useLogin } from "../api/auth";
import type { GlobalRole } from "../stores/uiStore";
import type { ProjectRole } from "../api/auth";

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

    // На всякий случай очищаем старое состояние пользователя
    logout();

    if (!login || !password) {
      setErrorText("Укажите логин и пароль.");
      return;
    }

    // ВАЖНО: бекенд ждёт поля username и password
    loginMutation.mutate(
      { username: login, password },
      {
        onSuccess: (data) => {
          // ТЕКУЩИЙ ФОРМАТ ОТВЕТА БЭКЕНДА (заглушка):
          // {
          //   access_token: "admin-token",
          //   token_type: "bearer",
          //   user: {
          //     id: "admin",
          //     global_role: "system",
          //     tenant_id: "...",
          //     email: "admin@example.com"
          //   }
          // }
          //
          // В будущем здесь будет реальный пользователь + JWT,
          // но структура userInfo в uiStore лучше оставить такой же.

          const user = data.user;

          // Базовые значения из бэка
          let globalRole: GlobalRole = "user";
          let projectRoles: Record<string, ProjectRole> = {};

          // DEV-режим:
          // Если логин admin (user.id === "admin"), считаем его супер-админом системы
          // и админом во всех проектах.
          if (user.id === "admin") {
            globalRole = "superadmin";
          } else {
            // Пока бэк возвращает произвольные строки, жёстко мапим только известные.
            if (user.global_role === "superadmin" || user.global_role === "user" || user.global_role === "system") {
              globalRole = user.global_role as GlobalRole;
            } else {
              globalRole = "user";
            }
          }
            // projectRoles заполним динамически в будущем;
            // пока логика RequireProjectRole при отсутствии ключа
            // поставит viewer, поэтому для теста загрузки можно вручную
            // прописывать нужный dealId в useAuth, как обсуждали.

          setUserInfo({
            userId: user.id,
            userName: user.email ?? user.id,
            globalRole,
            projectRoles,
            apiKey: data.access_token,
          });

          navigate("/dashboard");
        },
        onError: (err: any) => {
          // err приходит из Axios интерсептора как ApiError
          // Важно: рендерим строку, а не весь объект ошибки.
          const detail =
            err?.detail ||
            err?.message ||
            "Ошибка входа. Проверьте логин и пароль.";
          setErrorText(String(detail));
        },
      },
    );
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow border p-6">
        <h1 className="text-xl font-bold text-gray-900 mb-4">
          LegalMAS — Вход
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          Введите логин и пароль, выданные администратором.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          {/* Логин */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Логин
            </label>
            <input
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Ваш логин"
              autoComplete="username"
            />
          </div>

          {/* Пароль */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Пароль
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Ваш пароль"
              autoComplete="current-password"
            />
          </div>

          {/* Ошибка входа */}
          {errorText && (
            <p className="text-sm text-red-600">
              {errorText}
            </p>
          )}

          <button
            type="submit"
            disabled={loginMutation.isPending}
            className="w-full px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {loginMutation.isPending ? "Входим..." : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
