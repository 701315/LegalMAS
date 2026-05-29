// =============================================================
// src/hooks/useDeleteProject.ts
// =============================================================

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "../api/projects";
import { queryKeys } from "../api/queryKeys";

/**
 * Общий hook для удаления проекта.
 *
 * После успешного удаления инвалидирует кэш списка проектов
 * текущего пользователя. Это заставляет все активные подписчики
 * на этот query key (например Dashboard и AppShell) автоматически
 * перезапросить актуальные данные.
 *
 * Принимает string | null | undefined, чтобы напрямую
 * принимать значение userId из useAuth() без лишних преобразований
 * на стороне вызывающего компонента.
 *
 * @param userId Идентификатор пользователя, чей список проектов
 * должен быть обновлён после удаления.
 */
export function useDeleteProject(userId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dealId: string) => deleteProject(dealId),
    onSuccess: async () => {
      if (!userId) return;

      await queryClient.invalidateQueries({
        queryKey: queryKeys.userProjects(userId),
      });
    },
  });
}


