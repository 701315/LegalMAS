// =============================================================
// src/pages/tabs/RequestsTab.tsx
// Вкладка "Запросы": таблица DD‑запросов + side panel деталей.
// =============================================================

import React, { useCallback, useState } from "react";
import type { DDRequest } from "../../types";
import {
  useRequests,
  useUpdateRequest,
  useDeleteRequest,
  useExportRequests,
} from "../../api/requests";
import { RequestsTable } from "../../components/requests/RequestsTable";
import { RequestSidePanel } from "../../components/requests/RequestSidePanel";
import { Loader2 } from "lucide-react";

interface Props {
  dealId: string;
}

export const RequestsTab: React.FC<Props> = ({ dealId }) => {
  const { data: requests, isLoading } = useRequests(dealId);

  const updateMutation = useUpdateRequest(dealId);
  const deleteMutation = useDeleteRequest(dealId);
  const exportRequestsMutation = useExportRequests();

  const [selectedReq, setSelectedReq] = useState<DDRequest | null>(null);

  // Сохранение изменений из side panel
  const handleSave = useCallback(
    async (reqId: string, data: Partial<DDRequest>) => {
      await updateMutation.mutateAsync({ reqId, data });
    },
    [updateMutation],
  );

  // Удаление запроса
  const handleDelete = useCallback(
    async (reqId: string) => {
      await deleteMutation.mutateAsync(reqId);
    },
    [deleteMutation],
  );

  // Экспорт Word (список DD-запросов -> .docx)
  const handleExportWord = useCallback(async () => {
    try {
      const blob = await exportRequestsMutation.mutateAsync({
        dealId,
        format: "word",
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dd_requests_${dealId}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Не удалось экспортировать запросы в Word.");
    }
  }, [dealId, exportRequestsMutation]);

  // Экспорт Excel (список DD-запросов -> .xlsx)
  const handleExportExcel = useCallback(async () => {
    try {
      const blob = await exportRequestsMutation.mutateAsync({
        dealId,
        format: "excel",
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dd_requests_${dealId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Не удалось экспортировать запросы в Excel.");
    }
  }, [dealId, exportRequestsMutation]);

  // Создание нового запроса (плейсхолдер)
  const handleCreate = useCallback(() => {
    alert("Создание нового запроса будет реализовано позже.");
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin mr-3 text-blue-500" size={24} />
        <span className="text-lg text-gray-500">Загружаем запросы…</span>
      </div>
    );
  }

  return (
    <>
      <RequestsTable
        requests={requests ?? []}
        onRowClick={setSelectedReq}
        onCreateClick={handleCreate}
        onExportWord={handleExportWord}
        onExportExcel={handleExportExcel}
      />

      <RequestSidePanel
        request={selectedReq}
        onClose={() => setSelectedReq(null)}
        onSave={handleSave}
        onDelete={handleDelete}
        isSaving={updateMutation.isPending}
      />
    </>
  );
};

export default RequestsTab;
