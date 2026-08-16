// src/utils/apiErrors.ts

import type { ApiError } from "../types";

export function getApiErrorMessage(
  error: unknown,
  fallback = "Произошла ошибка.",
): string {
  const apiError = error as ApiError | null | undefined;
  const rawDetail: unknown = apiError?.detail;
  if (typeof rawDetail === "string") return rawDetail;
  if (
    typeof rawDetail === "object" &&
    rawDetail !== null &&
    "message" in rawDetail
  ) {
    return String((rawDetail as Record<string, unknown>).message);
  }
  return fallback;
}

export function getApiErrorStatus(error: unknown): number | undefined {
  const apiError = error as ApiError | null | undefined;
  return apiError?.status;
}

export function isApiErrorStatus(error: unknown, status: number): boolean {
  return getApiErrorStatus(error) === status;
}

