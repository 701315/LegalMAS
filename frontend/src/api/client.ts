// =============================================================
// src/api/client.ts
// Общий Axios-клиент для всех запросов к бэкенду MAS-DD.
// Добавляет Authorization: Bearer из localStorage.
// =============================================================

import axios from "axios";
import type { ApiError } from "../types";

// Базовый URL берём из Vite-окружения
const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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