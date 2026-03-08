// =============================================================
// src/api/client.ts
// Общий Axios-клиент для всех запросов к бэкенду MAS-DD.
// Добавляет baseURL и X-API-Key из localStorage.
// =============================================================

import axios from "axios";
import type { ApiError } from "../types";

// Базовый URL берём из Vite-окружения
const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";
// без /api/v1 тут


// Создаём инстанс axios
const client = axios.create({
  baseURL,
  timeout: 30_000,
});

// Интерсептор: добавляем X-API-Key к каждому запросу
client.interceptors.request.use((config) => {
  // TODO: позже можно взять ключ из Zustand-стора, а не из localStorage
  const apiKey = localStorage.getItem("mas_dd_api_key");
  if (apiKey) {
    config.headers = config.headers ?? {};
    config.headers["X-API-Key"] = apiKey;
  }
  return config;
});

// Интерсептор: базовая обработка ошибок
client.interceptors.response.use(
  (response) => response,
  (error) => {
    // Здесь можно сделать централизованный лог/redirect на login при 401
    const apiError: ApiError = {
      detail: error.response?.data?.detail || "Unknown error",
      code: error.response?.data?.code,
    };
    // Пробрасываем ошибку дальше, чтобы её поймали хуки/компоненты
    return Promise.reject(apiError);
  },
);

export default client;
