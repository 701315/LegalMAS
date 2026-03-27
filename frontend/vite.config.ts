// =============================================================
// vite.config.ts
// Конфигурация Vite + React + Tailwind v4
// =============================================================

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      // всё, что начинается с /api/v1, проксируем на FastAPI
      "/api/v1": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // путь на бекенде такой же (/api/v1/...), поэтому rewrite не нужен
      },
      // если где-то в коде есть старые запросы на /api/..., можно добавить:
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
