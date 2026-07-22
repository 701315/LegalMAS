// src/hooks/instructions/useInstructionOverrides.ts

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateDealOverride,
  activateTenantOverride,
  archiveDealOverride,
  archiveTenantOverride,
  createDealOverrideDraft,
  createTenantOverrideDraft,
  fetchDealOverrides,
  fetchTenantOverrides,
  rebaseDealOverride,
  validateDealOverride,
  validateTenantOverride,
} from "../../api/instructions/overrides";
import type {
  CreateOverrideDraftRequest,
  RebaseOverrideRequest,
} from "../../api/instructions/overrides";

// ─────────────────────────────────────────────────────────────
// Query Keys
// ─────────────────────────────────────────────────────────────

export const overrideQueryKeys = {
  tenantOverrides: (tenantId: string) =>
    ["tenant-overrides", tenantId] as const,
  dealOverrides: (dealId: string) =>
    ["deal-overrides", dealId] as const,
} as const;

// ─────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────

export function useTenantOverrides(tenantId: string | null) {
  return useQuery({
    queryKey: overrideQueryKeys.tenantOverrides(tenantId ?? ""),
    queryFn: () => fetchTenantOverrides(tenantId!),
    enabled: !!tenantId,
  });
}

export function useDealOverrides(dealId: string | null) {
  return useQuery({
    queryKey: overrideQueryKeys.dealOverrides(dealId ?? ""),
    queryFn: () => fetchDealOverrides(dealId!),
    enabled: !!dealId,
  });
}

// ─────────────────────────────────────────────────────────────
// Tenant mutations
// ─────────────────────────────────────────────────────────────

export function useCreateTenantOverrideDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      tenantId,
      body,
    }: {
      tenantId: string;
      body: CreateOverrideDraftRequest;
    }) => createTenantOverrideDraft(tenantId, body),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.tenantOverrides(variables.tenantId),
      });
    },
  });
}

export function useValidateTenantOverride() {
  return useMutation({
    mutationFn: ({
      tenantId,
      overrideId,
    }: {
      tenantId: string;
      overrideId: string;
    }) => validateTenantOverride(tenantId, overrideId),
  });
}

export function useActivateTenantOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      tenantId,
      overrideId,
    }: {
      tenantId: string;
      overrideId: string;
    }) => activateTenantOverride(tenantId, overrideId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.tenantOverrides(variables.tenantId),
      });
    },
  });
}

export function useArchiveTenantOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      tenantId,
      overrideId,
    }: {
      tenantId: string;
      overrideId: string;
    }) => archiveTenantOverride(tenantId, overrideId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.tenantOverrides(variables.tenantId),
      });
    },
  });
}

// ─────────────────────────────────────────────────────────────
// Deal mutations
// ─────────────────────────────────────────────────────────────

export function useCreateDealOverrideDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dealId,
      body,
    }: {
      dealId: string;
      body: CreateOverrideDraftRequest;
    }) => createDealOverrideDraft(dealId, body),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.dealOverrides(variables.dealId),
      });
    },
  });
}

export function useValidateDealOverride() {
  return useMutation({
    mutationFn: ({
      dealId,
      overrideId,
    }: {
      dealId: string;
      overrideId: string;
    }) => validateDealOverride(dealId, overrideId),
  });
}

export function useActivateDealOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dealId,
      overrideId,
    }: {
      dealId: string;
      overrideId: string;
    }) => activateDealOverride(dealId, overrideId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.dealOverrides(variables.dealId),
      });
    },
  });
}

export function useArchiveDealOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dealId,
      overrideId,
    }: {
      dealId: string;
      overrideId: string;
    }) => archiveDealOverride(dealId, overrideId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.dealOverrides(variables.dealId),
      });
    },
  });
}

export function useRebaseDealOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dealId,
      overrideId,
      body,
    }: {
      dealId: string;
      overrideId: string;
      body: RebaseOverrideRequest;
    }) => rebaseDealOverride(dealId, overrideId, body),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: overrideQueryKeys.dealOverrides(variables.dealId),
      });
    },
  });
}


