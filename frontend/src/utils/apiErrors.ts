// src/utils/apiErrors.ts

import type { ApiError } from "../types";

export function getApiErrorMessage(
  error: unknown,
  fallback = "Произошла ошибка.",
): string {
  const apiError = error as ApiError | null | undefined;
  return apiError?.detail || fallback;
}

export function getApiErrorStatus(error: unknown): number | undefined {
  const apiError = error as ApiError | null | undefined;
  return apiError?.status;
}

export function isApiErrorStatus(error: unknown, status: number): boolean {
  return getApiErrorStatus(error) === status;
}

