// src/utils/statusConfig.ts
// Единый конфиг отображения статусов документов и запусков (Run) в UI.
//
// Задача этого модуля:
// - дать одним местом все лейблы, цвета и "человеческие" названия стадий;
// - чтобы любые компоненты (таблицы, карточки, тултипы) не придумывали
//   свои подписи и цвета, а пользовались единым источником правды.
//
// Цвета условные — подстрой под свою дизайн-систему (primary/success/warning/error).

import type {
  DocumentStatus,
  RunStatus,
  ProcessingErrorDetails,
} from "../types";

// Цвет как простой string — дальше маппится на класс/токен дизайна.
export type StatusColor = "default" | "info" | "success" | "warning" | "error";

export interface DocumentStatusConfig {
  label: string; // Backward compatibility fallback (Russian)
  labelKey: string;
  color: StatusColor;
  tooltip?: string; // Backward compatibility fallback
  tooltipKey?: string;
  description?: string; // Backward compatibility fallback
  descriptionKey?: string;
}

export interface RunStatusConfig {
  label: string; // Backward compatibility fallback (Russian)
  labelKey: string;
  color: StatusColor;
}

/** Маппинг статуса документа в подпись, i18n-ключ и цвет. */
export const DOCUMENT_STATUS_CONFIG: Record<DocumentStatus, DocumentStatusConfig> = {
  pending: {
    label: "Ожидает обработки",
    labelKey: "pipeline:documentStatuses.pending",
    color: "default",
  },
  extracting: {
    label: "Извлечение текста",
    labelKey: "pipeline:documentStatuses.extracting",
    color: "info",
  },
  extracted: {
    label: "Текст извлечён",
    labelKey: "pipeline:documentStatuses.extracted",
    color: "info",
  },
  sanitized: {
    label: "PII скрыты",
    labelKey: "pipeline:documentStatuses.sanitized",
    color: "info",
  },
  structured: {
    label: "Structure built", // stable fallback
    labelKey: "pipeline:documentStatuses.structured",
    color: "info",
  },
  classified: {
    label: "Классификация выполнена",
    labelKey: "pipeline:documentStatuses.classified",
    color: "info",
  },
  analyzing: {
    label: "Выполняются проверки",
    labelKey: "pipeline:documentStatuses.analyzing",
    color: "info",
  },
  completed: {
    label: "Проверки выполнены",
    labelKey: "pipeline:documentStatuses.completed",
    color: "success",
  },
  quarantine: {
    label: "Карантин (нужна проверка)",
    labelKey: "pipeline:documentStatuses.quarantine",
    color: "warning",
  },
  failed: {
    label: "Ошибка обработки",
    labelKey: "pipeline:documentStatuses.failed",
    color: "error",
  },
  duplicate: {
    label: "Дубликат",
    labelKey: "pipeline:documentStatuses.duplicate",
    color: "default",
  },
  language_selection_required: {
    label: "Нужно выбрать язык",
    labelKey: "pipeline:documentStatuses.language_selection_required.label",
    color: "warning",
    tooltip:
      "Загрузка документов завершена. Дальнейшая обработка для многоязычных документов остановлена до выбора основного языка проверки. По умолчанию выбран русский язык.",
    tooltipKey: "pipeline:documentStatuses.language_selection_required.tooltip",
    description:
      "Загрузка документов завершена. Для документов, в которых определено несколько языков, дальнейшая обработка — приведение к одноязычности по выбранному основному языку проверки, а также экстракция, санитизация, построение структуры, чанкинг и классификация — не будет продолжена, пока не выбран основной язык проверки. По умолчанию установлен русский язык.",
    descriptionKey: "pipeline:documentStatuses.language_selection_required.description",
  },
};

/** Маппинг статуса Run в подпись, i18n-ключ и цвет. */
export const RUN_STATUS_CONFIG: Record<RunStatus, RunStatusConfig> = {
  pending: {
    label: "Ожидает запуска",
    labelKey: "pipeline:runStatuses.pending",
    color: "default",
  },
  running: {
    label: "Выполняется",
    labelKey: "pipeline:runStatuses.running",
    color: "info",
  },
  completed: {
    label: "Завершён",
    labelKey: "pipeline:runStatuses.completed",
    color: "success",
  },
  completed_with_errors: {
    label: "Завершён с ошибками",
    labelKey: "pipeline:runStatuses.completed_with_errors",
    color: "warning",
  },
  failed: {
    label: "Не удалось выполнить",
    labelKey: "pipeline:runStatuses.failed",
    color: "error",
  },
  cancelled: {
    label: "Отменён",
    labelKey: "pipeline:runStatuses.cancelled",
    color: "default",
  },
};

/** Человекочитаемые названия стадий пайплайна из processing_error_details.stage. */
const STAGE_LABELS: Record<string, string> = {
  import: "Импорт файла",
  extract: "Извлечение текста",
  pii: "Скрытие персональных данных",
  structure: "Построение структуры",
  classify: "Классификация",
  checks: "Проверки по плейбуку",
  export: "Формирование отчёта",
};

/**
 * Вернуть человекочитаемое название стадии ошибки по processing_error_details.
 *
 * Если stage неизвестен или отсутствует — возвращаем общий текст.
 * Поддерживает i18next TFunction, если она передана.
 */
export function getErrorStageLabel(
  details?: ProcessingErrorDetails | null,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!details || !details.stage) {
    return tFn ? tFn("pipeline:stages.unknown") : "Неизвестная стадия";
  }
  if (tFn) {
    const key = `pipeline:stages.${details.stage}`;
    const localized = tFn(key, { defaultValue: "" });
    if (localized) return localized;
  }
  return STAGE_LABELS[details.stage] ?? details.stage;
}


