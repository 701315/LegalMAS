// =============================================================
// src/api/documentTypes.ts
// API-функции и React Query хуки для работы с типами документов.
//
// Используется:
// - в контейнере правой панели документа (DocumentDetailsContainer)
//   для получения списка доступных типов документов;
// - при ручной переклассификации документа (выпадающий список типов).
//
// Backend-эндпоинт:
// - GET /api/v1/document-types
//   (см. src/api/endpoints/document_types.py).
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";

// Описание одного типа документа, как его отдаёт backend.
export interface DocumentTypeOption {
  // Внутренний код типа, например "contract_1.6_real_estate"
  type: string;
  // Человеко-понятное название типа
  name: string;
  // Основная категория: "contract", "annex" и т.п. (может быть null)
  category?: string | null;
  // Уровень риска: "low" / "medium" / "high" / "critical" (может быть null)
  risk_level?: string | null;
  // Основной язык документов этого типа (например, "ru", "en")
  language?: string | null;
  // Юрисдикция, например "RU", "EN"
  jurisdiction?: string | null;
}

// Низкоуровневая функция: один HTTP-запрос к backend.
async function fetchDocumentTypes(): Promise<DocumentTypeOption[]> {
  const { data } = await client.get<DocumentTypeOption[]>("/api/v1/document-types");
  return data;
}

/**
 * React Query хук для получения списка типов документов.
 *
 * Пример использования:
 *   const { data, isLoading, error } = useDocumentTypes();
 *   const availableDocTypes = (data ?? []).map((t) => t.type);
 */
export function useDocumentTypes() {
  return useQuery<DocumentTypeOption[], Error>({
    queryKey: ["document-types"],
    queryFn: fetchDocumentTypes,
    // Типы документов меняются редко, поэтому можно кэшировать подольше.
    staleTime: 10 * 60_000, // 10 минут
  });
}
