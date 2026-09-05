// =============================================================
// src/hooks/instructions/useETagConcurrency.ts
// Hook for managing ETag-based optimistic concurrency when editing drafts.
// =============================================================

import { useCallback, useRef, useState } from "react";
import type { ApiError } from "../../types";
import type {
  InstructionVersionDetailItem,
  InstructionVersionItem,
  GlobalInstructionVersionDetailItem,
  GlobalInstructionVersionItem,
} from "../../types/instructions";
import type { UpdateInstructionDraftRequest } from "../../api/instructions/playbooks";
import type { UpdateGlobalInstructionDraftRequest } from "../../api/instructions/globalInstructions";
import type { DetailWithETag } from "../../types/instructions";

export type ETagConcurrencyStatus =
  | "idle"
  | "loading"
  | "saving"
  | "success"
  | "stale"
  | "conflict"
  | "error";

// ── Generic types ──────────────────────────────────────────────
// Supports both doc-type and global instruction version drafts.

export type AnyVersionDetailItem =
  | InstructionVersionDetailItem
  | GlobalInstructionVersionDetailItem;

export type AnyVersionItem =
  | InstructionVersionItem
  | GlobalInstructionVersionItem;

export type AnyUpdateRequest =
  | UpdateInstructionDraftRequest
  | UpdateGlobalInstructionDraftRequest;

export interface ETagConcurrencyState {
  status: ETagConcurrencyStatus;
  conflictData?: AnyVersionDetailItem;
  errorMessage?: string;
}

export interface SaveDraftOptions {
  onSuccess?: (data: AnyVersionItem) => void;
  onConflict?: (freshData: AnyVersionDetailItem) => void;
  onError?: (message: string) => void;
}

export interface UseETagConcurrencyReturn {
  concurrencyState: ETagConcurrencyState;
  loadDetail: () => Promise<AnyVersionDetailItem | null>;
  saveDraft: (
    body: AnyUpdateRequest,
    options?: SaveDraftOptions,
  ) => Promise<boolean>;
  resetConcurrencyState: () => void;
  getCurrentEtag: () => string | null;
}

// ── Adapter functions injected by caller ───────────────────────

export interface ETagConcurrencyAdapters {
  /**
   * Fetches version detail + ETag.
   * Wraps either fetchInstructionVersionDetail or fetchGlobalInstructionVersionDetail.
   */
  fetchDetail: (
    versionId: string,
  ) => Promise<DetailWithETag<{ item: AnyVersionDetailItem }>>;

  /**
   * PATCHes the draft with ETag.
   * Wraps either updateInstructionDraft or updateGlobalInstructionDraft.
   */
  updateDraft: (
    versionId: string,
    body: AnyUpdateRequest,
    etag: string,
  ) => Promise<AnyVersionItem>;
}

// ── Hook ──────────────────────────────────────────────────────

export function useETagConcurrency(
  versionId: string,
  adapters: ETagConcurrencyAdapters,
): UseETagConcurrencyReturn {
  const etagRef = useRef<string | null>(null);

  const [concurrencyState, setConcurrencyState] =
    useState<ETagConcurrencyState>({ status: "idle" });

  const loadDetail = useCallback(
    async (): Promise<AnyVersionDetailItem | null> => {
      setConcurrencyState({ status: "loading" });
      try {
        const { data, etag } = await adapters.fetchDetail(versionId);
        etagRef.current = etag;
        setConcurrencyState({ status: "idle" });
        return data.item;
      } catch (err) {
        const apiErr = err as ApiError;
        const rawDetail: unknown = apiErr.detail;
        const errorMessage =
          typeof rawDetail === "string"
            ? rawDetail
            : typeof rawDetail === "object" &&
                rawDetail !== null &&
                "message" in rawDetail
              ? String((rawDetail as Record<string, unknown>).message)
              : "Failed to load instruction version.";
        setConcurrencyState({
          status: "error",
          errorMessage,
        });
        return null;
      }
    },
    [versionId, adapters.fetchDetail, adapters.updateDraft],
  );

  const saveDraft = useCallback(
    async (
      body: AnyUpdateRequest,
      options?: SaveDraftOptions,
    ): Promise<boolean> => {
      if (!etagRef.current) {
        const fresh = await loadDetail();
        if (!fresh || !etagRef.current) {
          return false;
        }
      }

      setConcurrencyState({ status: "saving" });

      try {
        const updatedItem = await adapters.updateDraft(
          versionId,
          body,
          etagRef.current!,
        );
        setConcurrencyState({ status: "success" });
        options?.onSuccess?.(updatedItem);
        return true;
      } catch (err) {
        const apiErr = err as ApiError;

        if (apiErr.status === 428) {
          etagRef.current = null;
          const fresh = await loadDetail();
          if (fresh) {
            setConcurrencyState({ status: "stale" });
          }
          return false;
        }

        if (apiErr.status === 412) {
          const fresh = await loadDetail();
          if (fresh) {
            setConcurrencyState({
              status: "conflict",
              conflictData: fresh,
            });
            options?.onConflict?.(fresh);
          }
          return false;
        }

        const rawDetail: unknown = apiErr.detail;
        const message =
          typeof rawDetail === "string"
            ? rawDetail
            : typeof rawDetail === "object" &&
                rawDetail !== null &&
                "message" in rawDetail
              ? String((rawDetail as Record<string, unknown>).message)
              : "Failed to save instruction draft.";
        setConcurrencyState({ status: "error", errorMessage: message });
        options?.onError?.(message);
        return false;
      }
    },
    [versionId, loadDetail, adapters],
  );

  const resetConcurrencyState = useCallback(() => {
    setConcurrencyState({ status: "idle" });
  }, []);

  const getCurrentEtag = useCallback(() => etagRef.current, []);

  return {
    concurrencyState,
    loadDetail,
    saveDraft,
    resetConcurrencyState,
    getCurrentEtag,
  };
}

// ── Pre-built adapters ─────────────────────────────────────────

import {
  fetchInstructionVersionDetail,
  updateInstructionDraft,
} from "../../api/instructions/playbooks";
import {
  fetchGlobalInstructionVersionDetail,
  updateGlobalInstructionDraft,
} from "../../api/instructions/globalInstructions";

/**
 * Adapters for doc-type instruction versions.
 */
export const docTypeETagAdapters: ETagConcurrencyAdapters = {
  fetchDetail: (versionId) => fetchInstructionVersionDetail(versionId),
  updateDraft: (versionId, body, etag) =>
    updateInstructionDraft(
      versionId,
      body as UpdateInstructionDraftRequest,
      etag,
    ),
};

/**
 * Adapters for global instruction versions.
 */
export const globalETagAdapters: ETagConcurrencyAdapters = {
  fetchDetail: (versionId) => fetchGlobalInstructionVersionDetail(versionId),
  updateDraft: (versionId, body, etag) =>
    updateGlobalInstructionDraft(
      versionId,
      body as UpdateGlobalInstructionDraftRequest,
      etag,
    ),
};


