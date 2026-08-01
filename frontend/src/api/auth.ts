// =============================================================
// src/api/auth.ts
// API-функции и React Query-хук для аутентификации (логин/пароль).
// =============================================================

import { useMutation } from "@tanstack/react-query";
import client from "./client";

// Роль пользователя в проекте (на будущее,
// сейчас в ответе /auth/login проектов ещё нет)
export type ProjectRole = "admin" | "editor" | "viewer";

// Описание одного проекта в ответе логина (пока не используется,
// но тип оставляем на будущее, когда бекенд начнёт его возвращать)
export interface LoginProjectEntry {
  deal_id: string;
  deal_name: string;
  role: ProjectRole;
  created_at: string;
}

// ТЕКУЩИЙ ответ от бэкенда на POST /api/v1/auth/login
// (см. src/api/endpoints/auth.py)
export interface LoginUser {
  id: string;
  global_role: string;
  tenant_id: string;
  email: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: LoginUser;
  // На будущее можно добавить сюда projects/api_key,
  // когда бекенд начнёт их возвращать.
}

// Тело запроса логина — то, что шлём на бекенд.
// Исторически поле называется username, но backend интерпретирует его как email.
export interface LoginInput {
  username: string;
  password: string;
}

// Низкоуровневый API-клиент
export const authApi = {
  /**
   * Логин по email и паролю.
   * POST /api/v1/auth/login
   */
  login: (data: LoginInput) =>
    client.post<LoginResponse>("/api/v1/auth/login", data).then((r) => r.data),
};

// React Query-хук для логина
export function useLogin() {
  return useMutation({
    mutationFn: (data: LoginInput) => authApi.login(data),
  });
}
