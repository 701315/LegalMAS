// =============================================================
// src/api/client.ts
// Общий Axios-клиент для всех запросов к бэкенду MAS-DD.
// Добавляет Authorization: Bearer из localStorage.
//
// Response interceptor:
// - при 401 очищает все mas_dd_* ключи из localStorage
// - редиректит на /login (одноразово, без цикла)
// - предотвращает бесконечный polling с протухшим токеном
// =============================================================

import axios from "axios";
import type { ApiError } from "../types";

// В production не уходим на localhost.
// Если VITE_API_URL не задан, используем same-origin:
// - в dev запросы /api/... пойдут через Vite proxy
// - в demo запросы /api/... пойдут через Caddy
const baseURL = (import.meta.env.VITE_API_URL ?? "").trim();

const client = axios.create({
  baseURL,
  timeout: 30_000,
});

// ── Auth cleanup helper ──────────────────────────────────────
// Ключи должны совпадать с тем, что использует useUIStore
// в logout() и в setUserInfo(). При изменении там — синхронизировать здесь.
const AUTH_STORAGE_KEYS = [
  "mas_dd_api_key",
  "mas_dd_user_role",
  "mas_dd_user_id",
  "mas_dd_user_name",
  "mas_dd_tenant_id",
  "mas_dd_global_role",
  "mas_dd_project_roles",
] as const;

// Флаг однократного редиректа: защита от гонок,
// когда несколько параллельных запросов сразу получают 401.
let authRedirectInFlight = false;

function handleUnauthorized(): void {
  if (authRedirectInFlight) {
    return;
  }
  authRedirectInFlight = true;

  // Чистим все auth-ключи из localStorage.
  // Стор при следующей загрузке страницы гидратируется как "не залогинен".
  try {
    for (const key of AUTH_STORAGE_KEYS) {
      localStorage.removeItem(key);
    }
  } catch {
    // localStorage может быть недоступен в приватном режиме — игнорируем.
  }

  // Уводим на /login. Полная перезагрузка гарантирует,
  // что все in-memory состояния (Zustand, React Query cache)
  // будут сброшены и не останутся "мёртвые" polling-запросы.
  if (typeof window !== "undefined") {
    const alreadyOnLogin =
      window.location.pathname === "/login" ||
      window.location.pathname.startsWith("/login");

    if (!alreadyOnLogin) {
      window.location.replace("/login");
    }
  }
}

// ── Request interceptor ──────────────────────────────────────
client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem("mas_dd_api_key");
  if (apiKey) {
    config.headers = config.headers ?? {};
    // JWT ожидает Authorization: Bearer <token>
    config.headers["Authorization"] = `Bearer ${apiKey}`;
  }
  return config;
});

// ── Response interceptor ─────────────────────────────────────
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;

    // При 401 — auth протух или невалиден.
    // Чистим сессию и уводим на /login.
    if (status === 401) {
      handleUnauthorized();
    }

    const apiError: ApiError = {
      detail: error?.response?.data?.detail || "Unknown error",
      code: error?.response?.data?.code,
      status: status,
    };
    return Promise.reject(apiError);
  },
);

export default client;


