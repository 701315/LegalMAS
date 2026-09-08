/**
 * Localization Review API — Sprint 6.6
 *
 * Exposes mutation hooks for QC translation review operations:
 * approve, reject, edit (human override), and reset.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import { dealReviewKeys } from "./dealReview";

export interface ReviewResponse {
  presentation_id: string;
  translation_status: string;
  locale: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  review_comment: string | null;
  has_human_override: boolean;
  has_original_snapshot: boolean;
}

export interface ReviewEditPayload {
  localized_check_name?: string | null;
  display_text?: string | null;
  review_message?: string | null;
  dd_request_text?: string | null;
  comment?: string | null;
}

// ── Mutation hooks ───────────────────────────────────────────────────

export function useApproveTranslation(dealId: string | null, runId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<ReviewResponse, Error, { presentationId: string; comment?: string | null }>({
    mutationFn: async ({ presentationId, comment }) => {
      const response = await client.post<ReviewResponse>(
        `/api/v1/localization-review/${presentationId}/approve`,
        { comment }
      );
      return response.data;
    },
    onSuccess: () => {
      // Invalidate DD Grid cache to reflect updated approved texts instantly
      if (dealId && runId) {
        void queryClient.invalidateQueries({
          queryKey: dealReviewKeys.ddGridV1Base(dealId, runId),
        });
      }
    },
  });
}

export function useRejectTranslation(dealId: string | null, runId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<ReviewResponse, Error, { presentationId: string; comment: string }>({
    mutationFn: async ({ presentationId, comment }) => {
      const response = await client.post<ReviewResponse>(
        `/api/v1/localization-review/${presentationId}/reject`,
        { comment }
      );
      return response.data;
    },
    onSuccess: () => {
      if (dealId && runId) {
        void queryClient.invalidateQueries({
          queryKey: dealReviewKeys.ddGridV1Base(dealId, runId),
        });
      }
    },
  });
}

export function useEditTranslation(dealId: string | null, runId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<ReviewResponse, Error, { presentationId: string; payload: ReviewEditPayload }>({
    mutationFn: async ({ presentationId, payload }) => {
      const response = await client.post<ReviewResponse>(
        `/api/v1/localization-review/${presentationId}/edit`,
        payload
      );
      return response.data;
    },
    onSuccess: () => {
      if (dealId && runId) {
        void queryClient.invalidateQueries({
          queryKey: dealReviewKeys.ddGridV1Base(dealId, runId),
        });
      }
    },
  });
}

export function useResetTranslation(dealId: string | null, runId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<ReviewResponse, Error, { presentationId: string }>({
    mutationFn: async ({ presentationId }) => {
      const response = await client.post<ReviewResponse>(
        `/api/v1/localization-review/${presentationId}/reset`
      );
      return response.data;
    },
    onSuccess: () => {
      if (dealId && runId) {
        void queryClient.invalidateQueries({
          queryKey: dealReviewKeys.ddGridV1Base(dealId, runId),
        });
        // Invalidate translation progress to trigger celery re-run status polling
        void queryClient.invalidateQueries({
          queryKey: ["resultPresentationProgress", dealId, runId],
        });
      }
    },
  });
}
