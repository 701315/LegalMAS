// =============================================================
// src/api/imports.ts
// API-функции для импорта документов (multipart upload).
// =============================================================

import client from "./client";
import type { ImportJob } from "../types";

export const importApi = {
  /**
   * Загрузка файлов для сделки.
   *
   * Backend endpoint (предполагаемый):
   *   POST /api/v1/deals/{deal_id}/imports
   *   body: multipart/form-data с полем "files"
   */
  upload: (dealId: string, files: FileList) => {
    const formData = new FormData();

    // Добавляем все выбранные файлы в FormData
    Array.from(files).forEach((file) => {
      formData.append("files", file);
    });

    return client
      .post<ImportJob>(`/api/v1/deals/${dealId}/imports`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((response) => response.data);
  },
};
