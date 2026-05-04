// =============================================================
// src/constants/index.ts
// Общие константы: роли, права, классификация, статусы DD-запросов.
// =============================================================

import type { UserRole } from "../types";

export const ROLE_LEVEL: Record<UserRole, number> = {
  viewer: 1,
  editor: 2,
  reviewer: 3,
  admin: 4,
  superadmin: 5,
};

export const canReclassify = (role: UserRole) => ROLE_LEVEL[role] >= 2;

export const canViewClassificationReport = (role: UserRole) =>
  ROLE_LEVEL[role] >= 2;

export const canViewYamlInstructions = (role: UserRole) =>
  ROLE_LEVEL[role] >= 4;

export const CLASSIFICATION_LEVELS: Record<
  string,
  {
    shortLabel: string;
    label: string;
    description: string;
    badgeClassName: string;
  }
> = {
  L0: {
    shortLabel: "L0",
    label: "L0 — Нет совпадений",
    description: "Тип документа не определён",
    badgeClassName:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
  },
  L1: {
    shortLabel: "L1",
    label: "L1 — Имя файла",
    description: "Классификация по имени файла",
    badgeClassName:
      "border-[var(--color-blue)]/18 bg-[var(--color-blue-highlight)] text-[var(--color-blue)]",
  },
  L2: {
    shortLabel: "L2",
    label: "L2 — Ключевые слова",
    description: "Классификация по ключевым словам",
    badgeClassName:
      "border-[var(--accent-primary)]/18 bg-[var(--accent-muted)] text-[var(--accent-primary)]",
  },
  L3: {
    shortLabel: "L3",
    label: "L3 — Семантика",
    description: "Семантический поиск (эмбеддинги)",
    badgeClassName:
      "border-[var(--color-purple)]/18 bg-[var(--color-purple-highlight)] text-[var(--color-purple)]",
  },
  L4: {
    shortLabel: "L4",
    label: "L4 — LLM",
    description: "Подтверждено языковой моделью",
    badgeClassName:
      "border-[var(--color-success)]/18 bg-[var(--color-success-highlight)] text-[var(--color-success)]",
  },
  L_manual: {
    shortLabel: "Manual",
    label: "Ручной override",
    description: "Тип задан вручную оператором",
    badgeClassName:
      "border-[var(--color-gold)]/18 bg-[var(--color-gold-highlight)] text-[var(--color-gold-hover)]",
  },
};

export const CONFIDENCE_THRESHOLDS = {
  LOW: 0.6,
  MEDIUM: 0.8,
  HIGH: 0.9,
};

export const DD_REQUEST_STATUS_DISPLAY: Record<string, string> = {
  open: "🔴 Открыт",
  in_progress: "🟡 В работе",
  resolved: "🟢 Закрыт",
};

export const DD_REQUEST_SOURCE_DISPLAY: Record<
  string,
  { label: string; color: string; icon: string }
> = {
  yaml_template: {
    label: "YAML-шаблон",
    color: "bg-purple-100 text-purple-800",
    icon: "⚡",
  },
  manual: {
    label: "Вручную",
    color: "bg-gray-100 text-gray-700",
    icon: "✍️",
  },
  aggregator: {
    label: "Автоматически",
    color: "bg-blue-100 text-blue-800",
    icon: "🤖",
  },
};

export const AUDIT_ACTION_LABEL: Record<string, string> = {
  IMPORT: "Импорт",
  EXPORT: "Экспорт",
  SANITIZE: "Обезличивание",
  QC_CONFIRM: "QC подтверждение",
  QC_REJECT: "QC отклонение",
  QC_OVERRIDE: "QC изменение",
  DOCUMENT_REPLACE: "Замена документа",
  RUN_START: "Запуск анализа",
  PLAYBOOK_PROMOTE: "Промоут playbook",
  SET_DEAL_PLAYBOOK: "Изменение playbook сделки",
  RECLASSIFY: "Переклассификация",
  YAML_INSTRUCTION_APPLY: "Применение YAML-инструкции",
};

export const EXPORT_TYPE_LABEL: Record<string, string> = {
  grid_xlsx: "DD Grid (Excel)",
  deal_summary_xlsx: "Deal Summary (Excel)",
  report_docx: "Отчёт DD (Word)",
};

