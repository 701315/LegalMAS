// src/api/admin.ts

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import client from "./client";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  users_count: number;
  deals_count: number;
}

export interface TenantCreate {
  name: string;
  slug: string;
  notes?: string | null;
}

export interface TenantUpdate {
  name?: string;
  notes?: string | null;
  clear_notes?: boolean;
}

export interface AdminUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  system_role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name?: string | null;
  system_role: "tenant_admin" | "member";
}

export interface UserUpdate {
  full_name?: string | null;
  clear_full_name?: boolean;
  system_role?: string;
  password?: string;
  is_active?: boolean;
}

// Проект клиента — то, что возвращает backend для superadmin.
// Поля соответствуют стандартной Deal-модели бэкенда.
// Если бэкенд возвращает иную структуру — скорректировать здесь.
export interface TenantDeal {
  id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
  created_by_email: string | null;
  documents_count: number;
  members_count: number;
}

// ── Query Keys ─────────────────────────────────────────────────────────────

export const adminKeys = {
  tenants: ["admin", "tenants"] as const,
  tenant: (id: string) => ["admin", "tenants", id] as const,
  tenantUsers: (tenantId: string) =>
    ["admin", "tenants", tenantId, "users"] as const,
  tenantDeals: (tenantId: string) =>
    ["admin", "tenants", tenantId, "deals"] as const,
};

// ── API functions ──────────────────────────────────────────────────────────

export const adminApi = {
  // ── Tenants ────────────────────────────────────────────────

  async listTenants(includeInactive = false): Promise<Tenant[]> {
    const res = await client.get<Tenant[]>("/api/v1/admin/tenants", {
      params: { include_inactive: includeInactive },
    });
    return res.data;
  },

  async getTenant(tenantId: string): Promise<Tenant> {
    const res = await client.get<Tenant>(
      `/api/v1/admin/tenants/${tenantId}`,
    );
    return res.data;
  },

  async createTenant(data: TenantCreate): Promise<Tenant> {
    const res = await client.post<Tenant>("/api/v1/admin/tenants", data);
    return res.data;
  },

  async updateTenant(
    tenantId: string,
    data: TenantUpdate,
  ): Promise<Tenant> {
    const res = await client.put<Tenant>(
      `/api/v1/admin/tenants/${tenantId}`,
      data,
    );
    return res.data;
  },

  async deactivateTenant(tenantId: string): Promise<Tenant> {
    const res = await client.patch<Tenant>(
      `/api/v1/admin/tenants/${tenantId}/deactivate`,
    );
    return res.data;
  },

  async activateTenant(tenantId: string): Promise<Tenant> {
    const res = await client.patch<Tenant>(
      `/api/v1/admin/tenants/${tenantId}/activate`,
    );
    return res.data;
  },

  // ── Users ──────────────────────────────────────────────────

  async listTenantUsers(
    tenantId: string,
    includeInactive = false,
  ): Promise<AdminUser[]> {
    const res = await client.get<AdminUser[]>(
      `/api/v1/admin/tenants/${tenantId}/users`,
      { params: { include_inactive: includeInactive } },
    );
    return res.data;
  },

  async createTenantUser(
    tenantId: string,
    data: UserCreate,
  ): Promise<AdminUser> {
    const res = await client.post<AdminUser>(
      `/api/v1/admin/tenants/${tenantId}/users`,
      data,
    );
    return res.data;
  },

  async updateTenantUser(
    tenantId: string,
    userId: string,
    data: UserUpdate,
  ): Promise<AdminUser> {
    const res = await client.put<AdminUser>(
      `/api/v1/admin/tenants/${tenantId}/users/${userId}`,
      data,
    );
    return res.data;
  },

  async deactivateTenantUser(
    tenantId: string,
    userId: string,
  ): Promise<AdminUser> {
    const res = await client.patch<AdminUser>(
      `/api/v1/admin/tenants/${tenantId}/users/${userId}/deactivate`,
    );
    return res.data;
  },

  // ── Deals (проекты клиента) ────────────────────────────────
  // Endpoint: GET /api/v1/admin/tenants/:tenantId/deals
  // Superadmin видит все проекты любого клиента.

  async listTenantDeals(tenantId: string): Promise<TenantDeal[]> {
    const res = await client.get<TenantDeal[]>(
      `/api/v1/admin/tenants/${tenantId}/deals`,
    );
    return res.data;
  },
};

// ── Hooks ──────────────────────────────────────────────────────────────────

export function useTenants(includeInactive = false) {
  return useQuery({
    queryKey: [...adminKeys.tenants, { includeInactive }],
    queryFn: () => adminApi.listTenants(includeInactive),
  });
}

export function useTenant(tenantId: string | null) {
  return useQuery({
    queryKey: adminKeys.tenant(tenantId ?? ""),
    queryFn: () => adminApi.getTenant(tenantId!),
    enabled: Boolean(tenantId),
  });
}

export function useTenantUsers(
  tenantId: string | null,
  includeInactive = false,
) {
  return useQuery({
    queryKey: [
      ...adminKeys.tenantUsers(tenantId ?? ""),
      { includeInactive },
    ],
    queryFn: () => adminApi.listTenantUsers(tenantId!, includeInactive),
    enabled: Boolean(tenantId),
  });
}

export function useTenantDeals(tenantId: string | null) {
  return useQuery({
    queryKey: adminKeys.tenantDeals(tenantId ?? ""),
    queryFn: () => adminApi.listTenantDeals(tenantId!),
    enabled: Boolean(tenantId),
  });
}

export function useCreateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TenantCreate) => adminApi.createTenant(data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.tenants });
    },
  });
}

export function useUpdateTenant(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TenantUpdate) =>
      adminApi.updateTenant(tenantId, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.tenants });
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenant(tenantId),
      });
    },
  });
}

export function useDeactivateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tenantId: string) => adminApi.deactivateTenant(tenantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.tenants });
    },
  });
}

export function useActivateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tenantId: string) => adminApi.activateTenant(tenantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.tenants });
    },
  });
}

export function useCreateTenantUser(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UserCreate) =>
      adminApi.createTenantUser(tenantId, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenantUsers(tenantId),
      });
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenant(tenantId),
      });
    },
  });
}

export function useUpdateTenantUser(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      data,
    }: {
      userId: string;
      data: UserUpdate;
    }) => adminApi.updateTenantUser(tenantId, userId, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenantUsers(tenantId),
      });
    },
  });
}

export function useDeactivateTenantUser(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      adminApi.deactivateTenantUser(tenantId, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenantUsers(tenantId),
      });
      await queryClient.invalidateQueries({
        queryKey: adminKeys.tenant(tenantId),
      });
    },
  });
}


