import type { UserRole } from "../types";

/**
 * Numeric hierarchy для сравнения ролей.
 *
 * Semantic (соответствует комментариям в types/auth.ts):
 * - superadmin        = 5  (highest)
 * - tenant_admin      = 4  (по контракту auth.ts — canonical алиас admin)
 * - admin (legacy)    = 4  (legacy alias для tenant_admin, сохранён для dev-совместимости)
 * - reviewer          = 3
 * - editor            = 2
 * - member            = 1  (tenant-level read-only user)
 * - viewer            = 1  (project-level read-only role)
 *
 * ВАЖНО: значения membership и viewer сравнены как эквивалентные read-only.
 * Если позже появятся capability-разграничения между member и viewer —
 * скорректировать здесь без изменения callers.
 */
export const ROLE_LEVEL: Record<UserRole, number> = {
  viewer: 1,
  member: 1,
  editor: 2,
  reviewer: 3,
  admin: 4,
  tenant_admin: 4,
  superadmin: 5,
};

export const canReclassify = (role: UserRole) => ROLE_LEVEL[role] >= 2;

export const canViewClassificationReport = (role: UserRole) =>
  ROLE_LEVEL[role] >= 2;

export const canViewYamlInstructions = (role: UserRole) =>
  ROLE_LEVEL[role] >= 4;

export interface ClassificationLevelConfig {
  shortLabel: string;
  label: string; // backward compatibility fallback
  labelKey: string;
  description: string; // backward compatibility fallback
  descriptionKey: string;
  badgeClassName: string;
}

export const CLASSIFICATION_LEVELS: Record<string, ClassificationLevelConfig> = {
  L0: {
    shortLabel: "L0",
    label: "L0 — Нет совпадений",
    labelKey: "pipeline:classificationLevels.L0.label",
    description: "Тип документа не определён",
    descriptionKey: "pipeline:classificationLevels.L0.description",
    badgeClassName:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
  },
  L1: {
    shortLabel: "L1",
    label: "L1 — Имя файла",
    labelKey: "pipeline:classificationLevels.L1.label",
    description: "Классификация по имени файла",
    descriptionKey: "pipeline:classificationLevels.L1.description",
    badgeClassName:
      "border-[var(--color-blue)]/18 bg-[var(--color-blue-highlight)] text-[var(--color-blue)]",
  },
  L2: {
    shortLabel: "L2",
    label: "L2 — Ключевые слова",
    labelKey: "pipeline:classificationLevels.L2.label",
    description: "Классификация по ключевым словам",
    descriptionKey: "pipeline:classificationLevels.L2.description",
    badgeClassName:
      "border-[var(--accent-primary)]/18 bg-[var(--accent-muted)] text-[var(--accent-primary)]",
  },
  L3: {
    shortLabel: "L3",
    label: "L3 — Семантика",
    labelKey: "pipeline:classificationLevels.L3.label",
    description: "Семантический поиск (эмбеддинги)",
    descriptionKey: "pipeline:classificationLevels.L3.description",
    badgeClassName:
      "border-[var(--color-purple)]/18 bg-[var(--color-purple-highlight)] text-[var(--color-purple)]",
  },
  L4: {
    shortLabel: "L4",
    label: "L4 — LLM",
    labelKey: "pipeline:classificationLevels.L4.label",
    description: "Подтверждено языковой моделью",
    descriptionKey: "pipeline:classificationLevels.L4.description",
    badgeClassName:
      "border-[var(--color-success)]/18 bg-[var(--color-success-highlight)] text-[var(--color-success)]",
  },
  L_manual: {
    shortLabel: "Manual",
    label: "Ручной override",
    labelKey: "pipeline:classificationLevels.L_manual.label",
    description: "Тип задан вручную оператором",
    descriptionKey: "pipeline:classificationLevels.L_manual.description",
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

export const DD_REQUEST_STATUS_KEYS: Record<string, string> = {
  open: "requests:status.open",
  in_progress: "requests:status.in_progress",
  resolved: "requests:status.resolved",
};

export interface DdRequestSourceConfig {
  label: string; // fallback
  labelKey: string;
  color: string;
  icon: string;
}

export const DD_REQUEST_SOURCE_DISPLAY: Record<string, DdRequestSourceConfig> = {
  yaml_template: {
    label: "YAML-шаблон",
    labelKey: "requests:source.yaml_template",
    color: "bg-purple-100 text-purple-800",
    icon: "⚡",
  },
  manual: {
    label: "Вручную",
    labelKey: "requests:source.manual",
    color: "bg-gray-100 text-gray-700",
    icon: "✍️",
  },
  aggregator: {
    label: "Автоматически",
    labelKey: "requests:source.aggregator",
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

export const AUDIT_ACTION_KEYS: Record<string, string> = {
  IMPORT: "common:auditActions.IMPORT",
  EXPORT: "common:auditActions.EXPORT",
  SANITIZE: "common:auditActions.SANITIZE",
  QC_CONFIRM: "common:auditActions.QC_CONFIRM",
  QC_REJECT: "common:auditActions.QC_REJECT",
  QC_OVERRIDE: "common:auditActions.QC_OVERRIDE",
  DOCUMENT_REPLACE: "common:auditActions.DOCUMENT_REPLACE",
  RUN_START: "common:auditActions.RUN_START",
  PLAYBOOK_PROMOTE: "common:auditActions.PLAYBOOK_PROMOTE",
  SET_DEAL_PLAYBOOK: "common:auditActions.SET_DEAL_PLAYBOOK",
  RECLASSIFY: "common:auditActions.RECLASSIFY",
  YAML_INSTRUCTION_APPLY: "common:auditActions.YAML_INSTRUCTION_APPLY",
};

export const EXPORT_TYPE_LABEL: Record<string, string> = {
  grid_xlsx: "DD Grid (Excel)",
  deal_summary_xlsx: "Deal Summary (Excel)",
  report_docx: "Отчёт DD (Word)",
};

export const EXPORT_TYPE_KEYS: Record<string, string> = {
  grid_xlsx: "exports:types.grid_xlsx",
  deal_summary_xlsx: "exports:types.deal_summary_xlsx",
  report_docx: "exports:types.report_docx",
};