// =============================================================
// src/hooks/useStalePlaybooks.ts
// Хук для получения списка stale playbook-версий.
//
// Источник: GET /api/v1/playbooks/stale
// Refresh: refetch() или автоматически после refresh-as-new
//          (через queryClient.invalidateQueries(["playbooks"])).
// =============================================================

import { useQuery } from "@tanstack/react-query";

import client from "../api/client";
import type {
  StalePlaybookItem,
  StalePlaybooksResponse,
} from "../types/playbooks";

export interface UseStalePlaybooksResult {
  data: StalePlaybooksResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  /** Map playbook_version_id -> StalePlaybookItem для O(1) lookup. */
  byId: Map<string, StalePlaybookItem>;
  refetch: () => void;
}

export function useStalePlaybooks(): UseStalePlaybooksResult {
  const query = useQuery<StalePlaybooksResponse>({
    queryKey: ["playbooks", "stale"],
    queryFn: async () => {
      const res = await client.get<StalePlaybooksResponse>(
        "/api/v1/playbooks/stale",
      );
      return res.data;
    },
    staleTime: 60_000,
  });

  const byId = new Map<string, StalePlaybookItem>();
  if (query.data) {
    for (const item of query.data.stale) {
      byId.set(item.playbook_version_id, item);
    }
  }

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    byId,
    refetch: () => {
      void query.refetch();
    },
  };
}
