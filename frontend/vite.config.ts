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

  optimizeDeps: {
    include: [
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "react-dom/client",
      "framer-motion",
    ],
  },

  server: {
    proxy: {
      "/api/v1": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },

  build: {
    // Warning limit — по умолчанию 500 KB.
    // Основной bundle с ag-grid + всеми страницами всё равно > 1 MB.
    chunkSizeWarningLimit: 1500,

    rollupOptions: {
      output: {
        manualChunks: {
          // ---------- Core React ----------
          "react-vendor": [
            "react",
            "react-dom",
            "react-router-dom",
          ],

          // ---------- Query / data layer ----------
          "query-vendor": [
            "@tanstack/react-query",
          ],

          // ---------- AG Grid (тяжёлая таблица) ----------
          "ag-grid-vendor": [
            "ag-grid-community",
            "ag-grid-react",
          ],

          // ---------- UI / icons ----------
          "ui-vendor": [
            "lucide-react",
            "framer-motion",
            "tailwind-merge",
          ],
        },
      },
    },
  },
});