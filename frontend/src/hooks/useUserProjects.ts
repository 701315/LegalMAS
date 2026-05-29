// =============================================================
// src/hooks/useUserProjects.ts
// =============================================================

import { useQuery } from "@tanstack/react-query";
import { fetchUserProjects } from "../api/projects";
import { queryKeys } from "../api/queryKeys";

/**
 * Общий hook для загрузки списка проектов пользователя.
 *
 * Все компоненты, вызывающие этот hook с одинаковым userId,
 * подписываются на один и тот же cache entry в React Query.
 * Благодаря этому Dashboard и AppShell синхронно отображают
 * одинаковое актуальное состояние данных.
 *
 * Принимает string | null | undefined, чтобы напрямую
 * принимать значение userId из useAuth() без лишних преобразований
 * на стороне вызывающего компонента.
 *
 * @param userId Идентификатор пользователя.
 */
export function useUserProjects(userId?: string | null) {
  return useQuery({
    queryKey: queryKeys.userProjects(userId ?? "anonymous"),
    queryFn: () => fetchUserProjects(userId!),
    enabled: Boolean(userId),
    staleTime: 60_000,
  });
}

