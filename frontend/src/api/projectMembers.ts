// =============================================================
// src/api/projectMembers.ts
// API-клиент и hooks для участников проекта.
// TanStack Query v5 safe version.
// =============================================================

import {
  useMutation,
  useQuery,
  useQueryClient,
  type MutationFunctionContext,
  type QueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import client from "./client";
import type { ProjectRole } from "./auth";

export interface ProjectMember {
  member_id: string;
  name: string;
  login: string;
  role: ProjectRole;
  created_at: string;
}

export interface CreateProjectMemberInput {
  name: string;
  login: string;
  password: string;
  role: ProjectRole;
}

export interface UpdateProjectMemberInput {
  name?: string;
  login?: string;
  password?: string;
  role?: ProjectRole;
}

export interface UpdateProjectMemberParams {
  memberId: string;
  data: UpdateProjectMemberInput;
}

export const projectMembersKeys = {
  all: ["project-members"] as const,
  byDeal: (dealId: string) => [...projectMembersKeys.all, dealId] as const,
  create: (dealId: string) =>
    [...projectMembersKeys.all, "create", dealId] as const,
  update: (dealId: string) =>
    [...projectMembersKeys.all, "update", dealId] as const,
  remove: (dealId: string) =>
    [...projectMembersKeys.all, "delete", dealId] as const,
};

export const projectMembersApi = {
  async list(dealId: string): Promise<ProjectMember[]> {
    const res = await client.get<ProjectMember[]>(
      `/api/v1/projects/${dealId}/members`,
    );
    return res.data;
  },

  async create(
    dealId: string,
    data: CreateProjectMemberInput,
  ): Promise<ProjectMember> {
    const res = await client.post<ProjectMember>(
      `/api/v1/projects/${dealId}/members`,
      data,
    );
    return res.data;
  },

  async update(
    dealId: string,
    memberId: string,
    data: UpdateProjectMemberInput,
  ): Promise<ProjectMember> {
    const res = await client.put<ProjectMember>(
      `/api/v1/projects/${dealId}/members/${memberId}`,
      data,
    );
    return res.data;
  },

  async remove(dealId: string, memberId: string): Promise<void> {
    await client.delete(`/api/v1/projects/${dealId}/members/${memberId}`);
  },
};

async function invalidateProjectMembers(
  queryClient: QueryClient,
  dealId: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: projectMembersKeys.byDeal(dealId),
  });
}

type ProjectMembersQueryOptions = Omit<
  UseQueryOptions<ProjectMember[], Error, ProjectMember[], readonly unknown[]>,
  "queryKey" | "queryFn" | "enabled"
>;

export function useProjectMembers(
  dealId: string | null,
  options?: ProjectMembersQueryOptions,
) {
  return useQuery({
    queryKey: dealId
      ? projectMembersKeys.byDeal(dealId)
      : projectMembersKeys.all,
    queryFn: () => projectMembersApi.list(dealId!),
    enabled: Boolean(dealId),
    ...options,
  });
}

export function useCreateProjectMember(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: projectMembersKeys.create(dealId),
    mutationFn: (
      data: CreateProjectMemberInput,
      _context: MutationFunctionContext,
    ) => projectMembersApi.create(dealId, data),
    onSuccess: async () => {
      await invalidateProjectMembers(queryClient, dealId);
    },
  });
}

export function useUpdateProjectMember(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: projectMembersKeys.update(dealId),
    mutationFn: (
      { memberId, data }: UpdateProjectMemberParams,
      _context: MutationFunctionContext,
    ) => projectMembersApi.update(dealId, memberId, data),
    onSuccess: async () => {
      await invalidateProjectMembers(queryClient, dealId);
    },
  });
}

export function useDeleteProjectMember(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: projectMembersKeys.remove(dealId),
    mutationFn: (
      memberId: string,
      _context: MutationFunctionContext,
    ) => projectMembersApi.remove(dealId, memberId),
    onSuccess: async () => {
      await invalidateProjectMembers(queryClient, dealId);
    },
  });
}


