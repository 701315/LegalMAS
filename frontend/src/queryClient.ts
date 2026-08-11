// =============================================================
// src/queryClient.ts
//
// Единственный экземпляр QueryClient для всего приложения.
// Вынесен из main.tsx, чтобы:
// - его можно было импортировать из stores (например, чистить cache в logout)
// - все invalidateQueries / setQueryData ссылались на один инстанс.
// =============================================================

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
    },
  },
});


