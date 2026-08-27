// =============================================================
// src/api/projects.ts
// =============================================================

import client from "./client";
import type { ProjectRole } from "./auth";

/**
 * Единая модель проекта пользователя, которая используется
 * в Dashboard, sidebar и других местах интерфейса.
 */
export interface UserProject {
  deal_id: string;
  deal_name: string;
  role: ProjectRole;
  created_at: string;
  contact_person?: string | null;
  needs_setup?: boolean;
  analysis_completed?: boolean;
  is_processing?: boolean;
}

/**
 * Загружает список проектов, к которым у пользователя есть доступ.
 *
 * @param userId Идентификатор пользователя.
 * @returns Массив проектов пользователя.
 */
export async function fetchUserProjects(userId: string): Promise<UserProject[]> {
  const res = await client.get<UserProject[]>(`/api/v1/user/${userId}/projects`);
  return res.data;
}

/**
 * Удаляет проект по его deal ID.
 *
 * @param dealId Идентификатор проекта.
 * @returns Promise без данных, если удаление прошло успешно.
 */
export async function deleteProject(dealId: string): Promise<void> {
  await client.delete(`/api/v1/deals/${dealId}`);
}

