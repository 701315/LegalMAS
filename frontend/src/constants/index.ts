// =============================================================
// src/constants/index.ts
// Общие константы: роли, права, классификация, статусы DD-запросов.
// =============================================================

import type { UserRole } from "../types";

// -------------------------------------------------------------
// РОЛИ И УРОВНИ ДОСТУПА
// -------------------------------------------------------------

/**
 * Внутренние числовые уровни для ролей.
 * Используются в canReclassify / canViewClassificationReport / canViewYamlInstructions.
 *
 * viewer   -> 1
 * editor   -> 2
 * reviewer -> 3
 * admin    -> 4
 */
export const ROLE_LEVEL: Record<UserRole, number> = {
  viewer: 1,
  editor: 2,
  reviewer: 3,
  admin: 4,
};

// -------------------------------------------------------------
// ПРАВА ДОСТУПА (FRONTEND-HELPERS)
// -------------------------------------------------------------

/** Editor+ может вручную переклассифицировать документ */
export const canReclassify = (role: UserRole) => ROLE_LEVEL[role] >= 2;

/** Editor+ может просматривать classification report */
export const canViewClassificationReport = (role: UserRole) =>
  ROLE_LEVEL[role] >= 2;

/** Admin может просматривать YAML-инструкции */
export const canViewYamlInstructions = (role: UserRole) =>
  ROLE_LEVEL[role] >= 4;

// -------------------------------------------------------------
// УРОВНИ КЛАССИФИКАЦИИ
// -------------------------------------------------------------

/**
 * Настройки отображения уровней классификации L0–L4, L_manual.
 * color — Tailwind-классы для бейджа.
 */
export const CLASSIFICATION_LEVELS: Record<
  string,
  {
    label: string;
    description: string;
    color: string;
  }
> = {
  L0: {
    label: "L0 — Нет совпадений",
    description: "Тип документа не определён",
    color: "bg-gray-200 text-gray-700",
  },
  L1: {
    label: "L1 — Имя файла",
    description: "Классификация по имени файла",
    color: "bg-blue-100 text-blue-700",
  },
  L2: {
    label: "L2 — Ключевые слова",
    description: "Классификация по ключевым словам",
    color: "bg-indigo-100 text-indigo-700",
  },
  L3: {
    label: "L3 — Семантика",
    description: "Семантический поиск (эмбеддинги)",
    color: "bg-purple-100 text-purple-700",
  },
  L4: {
    label: "L4 — LLM",
    description: "Подтверждено языковой моделью",
    color: "bg-green-100 text-green-700",
  },
  L_manual: {
    label: "Ручной override",
    description: "Тип задан вручную оператором",
    color: "bg-yellow-100 text-yellow-800",
  },
};

// -------------------------------------------------------------
// ПОРОГИ УВЕРЕННОСТИ КЛАССИФИКАЦИИ
// -------------------------------------------------------------

/**
 * Пороги уверенности классификации.
 * LOW = 0.6 — ниже считается low_confidence (синхронизировано с бэкендом).
 */
export const CONFIDENCE_THRESHOLDS = {
  LOW: 0.6, // ниже — требует проверки
  MEDIUM: 0.8, // ниже — рекомендуется проверить
  HIGH: 0.9, // >= HIGH — высокая уверенность
};

// -------------------------------------------------------------
// DD ЗАПРОСЫ — СТАТУСЫ И ИСТОЧНИКИ
// -------------------------------------------------------------

/** Читаемые статусы DD-запросов для UI */
export const DD_REQUEST_STATUS_DISPLAY: Record<string, string> = {
  open: "🔴 Открыт",
  in_progress: "🟡 В работе",
  resolved: "🟢 Закрыт",
};

/** Читаемые источники DD-запросов для UI */
export const DD_REQUEST_SOURCE_DISPLAY: Record<string, string> = {
  yaml_template: "Шаблон YAML",
  manual: "Создан вручную",
  aggregator: "Автоматически",
};
