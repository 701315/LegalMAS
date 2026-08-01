// =============================================================
// src/api/client.ts
// Общий Axios-клиент для всех запросов к бэкенду MAS-DD.
// Добавляет Authorization: Bearer из localStorage.
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

// Интерсептор: добавляем Authorization: Bearer к каждому запросу
client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem("mas_dd_api_key");
  if (apiKey) {
    config.headers = config.headers ?? {};
    // JWT ожидает Authorization: Bearer <token>
    config.headers["Authorization"] = `Bearer ${apiKey}`;
  }
  return config;
});

// Интерсептор: базовая обработка ошибок
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError: ApiError = {
      detail: error.response?.data?.detail || "Unknown error",
      code: error.response?.data?.code,
      status: error.response?.status,
    };
    return Promise.reject(apiError);
  },
);

export default client;