// =============================================================
// src/api/projectMembers.ts
// API-клиент и хуки для участников проекта.
// =============================================================

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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

// Низкоуровневый API
export const projectMembersApi = {
  list: (dealId: string) =>
    client
      .get<ProjectMember[]>(`/api/v1/projects/${dealId}/members`)
      .then((r) => r.data),

  create: (dealId: string, data: CreateProjectMemberInput) =>
    client
      .post<ProjectMember>(`/api/v1/projects/${dealId}/members`, data)
      .then((r) => r.data),

  update: (
    dealId: string,
    memberId: string,
    data: UpdateProjectMemberInput,
  ) =>
    client
      .put<ProjectMember>(
        `/api/v1/projects/${dealId}/members/${memberId}`,
        data,
      )
      .then((r) => r.data),

  remove: (dealId: string, memberId: string) =>
    client
      .delete<void>(`/api/v1/projects/${dealId}/members/${memberId}`)
      .then((r) => r.data),
};

// Хук для списка участников
export function useProjectMembers(dealId: string | null) {
  return useQuery({
    queryKey: ["project-members", dealId],
    queryFn: () => projectMembersApi.list(dealId!),
    enabled: !!dealId,
  });
}

// Хуки для мутаций
export function useCreateProjectMember(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateProjectMemberInput) =>
      projectMembersApi.create(dealId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project-members", dealId] });
    },
  });
}

export function useUpdateProjectMember(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      memberId: string;
      data: UpdateProjectMemberInput;
    }) => projectMembersApi.update(dealId, params.memberId, params.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project-members", dealId] });
    },
  });
}

export function useDeleteProjectMember(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) =>
      projectMembersApi.remove(dealId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project-members", dealId] });
    },
  });
}
