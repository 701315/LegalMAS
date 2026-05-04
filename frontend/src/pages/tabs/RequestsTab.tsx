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
  onOpenViewerAt?: OpenViewerAtFn;
}

export const RequestsTab: React.FC<Props> = ({
  dealId,
  runId,
  onOpenViewerAt,
}) => {
  const { data: requests, isLoading } = useRequests(dealId);

  const updateMutation = useUpdateRequest(dealId);
  const deleteMutation = useDeleteRequest(dealId);
  const exportRequestsMutation = useExportRequests();

  const perms = useDealPermissions(dealId);
  const { canManageRequests } = perms;

  const [selectedReq, setSelectedReq] = useState<DDRequest | null>(null);
  const [selectedReviewReq, setSelectedReviewReq] = useState<DDRequestDTO | null>(
    null,
  );

  const { data: reviewRequests, isLoading: isLoadingReview } =
    useDealReviewDdRequests(dealId, runId ?? null, {
      enabled: !!runId,
    });

  const isReviewMode = !!runId && !isLoadingReview && Array.isArray(reviewRequests);

  const handleSave = useCallback(
    async (reqId: string, data: Partial<DDRequest>) => {
      if (!canManageRequests) return;
      await updateMutation.mutateAsync({ reqId, data });
    },
    [updateMutation, canManageRequests],
  );

  const handleDelete = useCallback(
    async (reqId: string) => {
      if (!canManageRequests) return;
      await deleteMutation.mutateAsync(reqId);
    },
    [deleteMutation, canManageRequests],
  );

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

  const handleCreate = useCallback(() => {
    if (!canManageRequests) {
      alert("Создание запросов доступно только редакторам и администраторам.");
      return;
    }
    alert("Создание нового запроса будет реализовано позже.");
  }, [canManageRequests]);

  if (isLoading && !isReviewMode) {
    return (
      <div className="flex min-h-[320px] items-center justify-center bg-[var(--bg-base)]">
        <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 text-[var(--text-secondary)] shadow-2xl shadow-black/30">
          <Loader2 className="animate-spin text-indigo-400" size={20} />
          <span className="text-sm">Загружаем запросы…</span>
        </div>
      </div>
    );
  }

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


