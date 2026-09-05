// =============================================================
// src/api/client.ts
// Shared Axios client for all backend API requests.
// Automatically attaches Authorization: Bearer token from localStorage.
//
// Response interceptor:
// - on 401, clears all mas_dd_* keys from localStorage
// - redirects to /login (once, without looping)
// - prevents infinite polling with expired tokens
// =============================================================

import axios from "axios";
import type { ApiError } from "../types";

// In production, do not hardcode localhost.
// If VITE_API_URL is omitted, use same-origin:
// - in dev mode, /api/... requests are proxied by Vite
// - in production/demo, /api/... requests are routed via reverse proxy (Caddy/Nginx)
const baseURL = (import.meta.env.VITE_API_URL ?? "").trim();

const client = axios.create({
  baseURL,
  timeout: 30_000,
});

// ── Auth cleanup helper ──────────────────────────────────────
// Keys must match those used by useUIStore in logout() and setUserInfo().
const AUTH_STORAGE_KEYS = [
  "mas_dd_api_key",
  "mas_dd_user_role",
  "mas_dd_user_id",
  "mas_dd_user_name",
  "mas_dd_tenant_id",
  "mas_dd_global_role",
  "mas_dd_project_roles",
] as const;

// Single redirect flight flag: prevents race conditions
// when multiple concurrent requests encounter 401 simultaneously.
let authRedirectInFlight = false;

function handleUnauthorized(): void {
  if (authRedirectInFlight) {
    return;
  }
  authRedirectInFlight = true;

  // Clear all auth-related keys from localStorage.
  // The store will hydrate as unauthenticated on the next page load.
  try {
    for (const key of AUTH_STORAGE_KEYS) {
      localStorage.removeItem(key);
    }
  } catch {
    // localStorage might be unavailable in private browser modes — safely ignore.
  }

  // Redirect to /login. A full replace navigation ensures that all
  // in-memory state (Zustand, React Query cache) is wiped clean and no
  // orphan polling requests remain active.
  if (typeof window !== "undefined") {
    const alreadyOnLogin =
      window.location.pathname === "/login" ||
      window.location.pathname.startsWith("/login");

    if (!alreadyOnLogin) {
      window.location.replace("/login");
    }
  }
}

// ── Request interceptor ──────────────────────────────────────
client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem("mas_dd_api_key");
  if (apiKey) {
    config.headers = config.headers ?? {};
    // JWT format requires Authorization: Bearer <token>
    config.headers["Authorization"] = `Bearer ${apiKey}`;
  }
  return config;
});

// ── Response interceptor ─────────────────────────────────────
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;

    // On 401 — auth token is expired or invalid.
    // Clean up session and redirect to /login.
    if (status === 401) {
      handleUnauthorized();
    }

    const apiError: ApiError = {
      detail: error?.response?.data?.detail || "Unknown error",
      code: error?.response?.data?.code,
      status: status,
    };
    return Promise.reject(apiError);
  },
);

export default client;


