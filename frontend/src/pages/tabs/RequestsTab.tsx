// =============================================================
// src/pages/tabs/RequestsTab.tsx
// Вкладка "Запросы": таблица DD‑запросов + side panel деталей.
// =============================================================

import React, { useCallback, useState } from "react";
import type { DDRequest, OpenViewerAtFn } from "../../types";
import {
  useRequests,
  useUpdateRequest,
  useDeleteRequest,
  useExportRequests,
} from "../../api/requests";
import { RequestsTable } from "../../components/requests/RequestsTable";
import { RequestSidePanel } from "../../components/requests/RequestSidePanel";
import { Loader2 } from "lucide-react";
import { useDealPermissions } from "../../hooks/usePermissions";

import { useDealReviewDdRequests } from "../../api/dealReview";
import type { DDRequestDTO } from "../../types/dealReview";
import { ReviewRequestsTable } from "../../components/requests/ReviewRequestsTable";
import { ReviewRequestSidePanel } from "../../components/requests/ReviewRequestSidePanel";

interface Props {
  dealId: string;
  runId: string | null;
  /**
   * Callback для открытия viewer в конкретном месте документа.
   * Передаётся из родительского компонента (например, DealPage).
   */
  onOpenViewerAt?: OpenViewerAtFn;
}

export const RequestsTab: React.FC<Props> = ({ dealId, runId, onOpenViewerAt }) => {
  const { data: requests, isLoading } = useRequests(dealId);

  const updateMutation = useUpdateRequest(dealId);
  const deleteMutation = useDeleteRequest(dealId);
  const exportRequestsMutation = useExportRequests();

  const perms = useDealPermissions(dealId);
  const { canManageRequests } = perms;

  console.log("deal permissions", dealId, JSON.stringify(perms, null, 2));

  const [selectedReq, setSelectedReq] = useState<DDRequest | null>(null);
  const [selectedReviewReq, setSelectedReviewReq] = useState<DDRequestDTO | null>(null);

  // Run-scoped DD requests — segment-aware, read-only review view.
  // Включается только если runId передан в пропсах.
  const { data: reviewRequests, isLoading: isLoadingReview } =
    useDealReviewDdRequests(dealId, runId ?? null, {
      enabled: !!runId,
    });

  // Режим: если есть runId и review-данные загружены — показываем review-режим.
  // Иначе — legacy-режим.
  const isReviewMode = !!runId && !isLoadingReview && Array.isArray(reviewRequests);

  // Сохранение изменений из side panel
  const handleSave = useCallback(
    async (reqId: string, data: Partial<DDRequest>) => {
      if (!canManageRequests) return;
      await updateMutation.mutateAsync({ reqId, data });
    },
    [updateMutation, canManageRequests],
  );

  // Удаление запроса
  const handleDelete = useCallback(
    async (reqId: string) => {
      if (!canManageRequests) return;
      await deleteMutation.mutateAsync(reqId);
    },
    [deleteMutation, canManageRequests],
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
    if (!canManageRequests) {
      alert("Создание запросов доступно только редакторам и администраторам.");
      return;
    }
    alert("Создание нового запроса будет реализовано позже.");
  }, [canManageRequests]);

  if (isLoading && !isReviewMode) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin mr-3 text-blue-500" size={24} />
        <span className="text-lg text-gray-500">Загружаем запросы…</span>
      </div>
    );
  }

  // Review-режим: run-scoped, segment-aware, read-only
  if (isReviewMode) {
    return (
      <>
        <ReviewRequestsTable
          requests={reviewRequests ?? []}
          onRowClick={setSelectedReviewReq}
        />
        <ReviewRequestSidePanel
          request={selectedReviewReq}
          onClose={() => setSelectedReviewReq(null)}
          onOpenAtLocation={onOpenViewerAt}
        />
      </>
    );
  }

  // Legacy-режим: управление запросами (CRUD)
  return (
    <>
      <RequestsTable
        requests={requests ?? []}
        onRowClick={setSelectedReq}
        onCreateClick={handleCreate}
        onExportWord={handleExportWord}
        onExportExcel={handleExportExcel}
        canManageRequests={canManageRequests}
      />
      <RequestSidePanel
        request={selectedReq}
        onClose={() => setSelectedReq(null)}
        onSave={handleSave}
        onDelete={handleDelete}
        isSaving={updateMutation.isPending}
        canManageRequests={canManageRequests}
      />
    </>
  );
};

export default RequestsTab;


