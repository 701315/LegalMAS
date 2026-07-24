// frontend/src/api/tenantPlaybooks.ts
//
// Read-only каталог tenant-owned playbooks организации.
// Endpoint: GET /api/v1/tenants/{tenant_id}/playbooks

import { useQuery } from "@tanstack/react-query";
import client from "./client";

export interface TenantPlaybookItem {
  id: string;
  code: string;
  title: string;
  description: string | null;
  deal_type: string | null;
  jurisdiction: string | null;
  language: string | null;
  risk_profile: string | null;
}

export const tenantPlaybookQueryKeys = {
  list: (tenantId: string) =>
    ["tenant-playbooks", tenantId] as const,
} as const;

export function useTenantOwnedPlaybooks(tenantId: string | null) {
  return useQuery({
    queryKey: tenantPlaybookQueryKeys.list(tenantId ?? ""),
    queryFn: async () => {
      const res = await client.get<TenantPlaybookItem[]>(
        `/api/v1/tenants/${tenantId}/playbooks`,
      );
      return res.data;
    },
    enabled: !!tenantId,
    staleTime: 30_000,
  });
}



