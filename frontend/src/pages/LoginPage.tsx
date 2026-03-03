// =============================================================
// src/pages/LoginPage.tsx
// Простейшая страница входа: API-ключ + выбор роли.
// =============================================================

import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import type { UserRole } from "../types";

interface LoginPageProps {
  /** Опциональный колбэк, который вызывается после успешного логина */
  onLoggedIn?: () => void;
}

const ROLES: UserRole[] = ["viewer", "editor", "reviewer", "admin"];

const LoginPage: React.FC<LoginPageProps> = ({ onLoggedIn }) => {
  const { apiKey, userRole, setApiKey, setUserRole } = useAuth();
  const [keyInput, setKeyInput] = useState(apiKey ?? "");
  const [roleInput, setRoleInput] = useState<UserRole>(userRole);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Сохраняем в store и localStorage
    setApiKey(keyInput || null);
    setUserRole(roleInput);

    // После логина можно перейти на список сделок
    if (onLoggedIn) {
      onLoggedIn();
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow border p-6">
        <h1 className="text-xl font-bold text-gray-900 mb-4">
          MAS-DD — Вход
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          Укажите API-ключ и роль пользователя для работы с системой.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          {/* API-ключ */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API-ключ
            </label>
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="X-API-Key для бэкенда MAS-DD"
            />
            <p className="text-xs text-gray-400 mt-1">
              Ключ будет сохранён только в localStorage этого браузера.
            </p>
          </div>

          {/* Роль */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Роль
            </label>
            <select
              value={roleInput}
              onChange={(e) => setRoleInput(e.target.value as UserRole)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              editor/reviewer/admin дают больше прав (переклассификация, отчёты).
            </p>
          </div>

          <button
            type="submit"
            className="w-full px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            Войти
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
