// src/api/instructions/overrides.ts
// API функции для instruction overrides.
// Tenant-level и deal-level endpoints.

import client from "../client";
import type {
  InstructionOverrideListResponse,
  InstructionOverrideResponse,
  InstructionOverrideValidationResponse,
  CreateOverrideDraftRequest,
  RebaseOverrideRequest,
  InstructionOverrideItem,
} from "../../types/instructions";

// Реэкспортируем для удобства импорта из hooks
export type {
  CreateOverrideDraftRequest,
  RebaseOverrideRequest,
};

// ─────────────────────────────────────────────────────────────
// Tenant-level overrides
// ─────────────────────────────────────────────────────────────

/**
 * GET /api/v1/tenants/:tenantId/instruction-overrides
 */
export async function fetchTenantOverrides(
  tenantId: string,
): Promise<InstructionOverrideListResponse> {
  const res = await client.get<InstructionOverrideListResponse>(
    `/api/v1/tenants/${tenantId}/instruction-overrides`,
  );
  return res.data;
}

/**
 * POST /api/v1/tenants/:tenantId/instruction-overrides/draft
 */
export async function createTenantOverrideDraft(
  tenantId: string,
  body: CreateOverrideDraftRequest,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/tenants/${tenantId}/instruction-overrides/draft`,
    body,
  );
  return res.data.item;
}

/**
 * POST /api/v1/tenants/:tenantId/instruction-overrides/:overrideId/validate
 */
export async function validateTenantOverride(
  tenantId: string,
  overrideId: string,
): Promise<InstructionOverrideValidationResponse> {
  const res = await client.post<InstructionOverrideValidationResponse>(
    `/api/v1/tenants/${tenantId}/instruction-overrides/${overrideId}/validate`,
  );
  return res.data;
}

/**
 * POST /api/v1/tenants/:tenantId/instruction-overrides/:overrideId/activate
 * Нельзя активировать stale override — backend вернёт 409.
 */
export async function activateTenantOverride(
  tenantId: string,
  overrideId: string,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/tenants/${tenantId}/instruction-overrides/${overrideId}/activate`,
  );
  return res.data.item;
}

/**
 * POST /api/v1/tenants/:tenantId/instruction-overrides/:overrideId/archive
 */
export async function archiveTenantOverride(
  tenantId: string,
  overrideId: string,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/tenants/${tenantId}/instruction-overrides/${overrideId}/archive`,
  );
  return res.data.item;
}

// ─────────────────────────────────────────────────────────────
// Deal-level overrides
// ─────────────────────────────────────────────────────────────

/**
 * GET /api/v1/deals/:dealId/instruction-overrides
 */
export async function fetchDealOverrides(
  dealId: string,
): Promise<InstructionOverrideListResponse> {
  const res = await client.get<InstructionOverrideListResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides`,
  );
  return res.data;
}

/**
 * POST /api/v1/deals/:dealId/instruction-overrides/draft
 */
export async function createDealOverrideDraft(
  dealId: string,
  body: CreateOverrideDraftRequest,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides/draft`,
    body,
  );
  return res.data.item;
}

/**
 * POST /api/v1/deals/:dealId/instruction-overrides/:overrideId/validate
 */
export async function validateDealOverride(
  dealId: string,
  overrideId: string,
): Promise<InstructionOverrideValidationResponse> {
  const res = await client.post<InstructionOverrideValidationResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides/${overrideId}/validate`,
  );
  return res.data;
}

/**
 * POST /api/v1/deals/:dealId/instruction-overrides/:overrideId/activate
 */
export async function activateDealOverride(
  dealId: string,
  overrideId: string,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides/${overrideId}/activate`,
  );
  return res.data.item;
}

/**
 * POST /api/v1/deals/:dealId/instruction-overrides/:overrideId/archive
 */
export async function archiveDealOverride(
  dealId: string,
  overrideId: string,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides/${overrideId}/archive`,
  );
  return res.data.item;
}

/**
 * POST /api/v1/deals/:dealId/instruction-overrides/:overrideId/rebase
 * Явный rebase на новую base version. Сбрасывает is_stale.
 */
export async function rebaseDealOverride(
  dealId: string,
  overrideId: string,
  body: RebaseOverrideRequest,
): Promise<InstructionOverrideItem> {
  const res = await client.post<InstructionOverrideResponse>(
    `/api/v1/deals/${dealId}/instruction-overrides/${overrideId}/rebase`,
    body,
  );
  return res.data.item;
}


