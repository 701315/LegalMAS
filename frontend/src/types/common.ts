// =============================================================
// src/types/common.ts
// Общие вспомогательные типы для всего frontend-а.
// =============================================================

/** Универсальный ответ с пагинацией для списков */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;

  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

/** Стандартная ошибка API */
export interface ApiError {
  detail: string;
  code?: string;
  status?: number; // HTTP-статус (404, 500 и т.п.)
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

  