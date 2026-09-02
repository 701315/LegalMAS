// =============================================================
// src/main.tsx
// Точка входа: Router + QueryClientProvider + AppRoutes.
//
// queryClient вынесен в отдельный модуль (./queryClient), чтобы его
// мог импортировать не только React, но и Zustand-store (для clear()
// на logout).
// =============================================================

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import "./i18n/config"; // Инициализация i18n перед загрузкой App
import App from "./App";
import "./index.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import {
  ModuleRegistry,
  AllCommunityModule,
  provideGlobalGridOptions,
} from "ag-grid-community";

import { queryClient } from "./queryClient";

ModuleRegistry.registerModules([AllCommunityModule]);

provideGlobalGridOptions({
  theme: "legacy",
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
);


