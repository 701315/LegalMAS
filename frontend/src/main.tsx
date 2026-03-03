// =============================================================
// src/main.tsx
// Точка входа: QueryClientProvider + рендер <App />.
// =============================================================

import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

// Создаём общий QueryClient для всего приложения
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // базовые настройки можно будет подправить позже
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
