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
  label: string;
  color: StatusColor;
  tooltip?: string;
  description?: string;
}

export interface RunStatusConfig {
  label: string;
  color: StatusColor;
}

/** Маппинг статуса документа в подпись и цвет. */
export const DOCUMENT_STATUS_CONFIG: Record<DocumentStatus, DocumentStatusConfig> = {
  pending: {
    label: "Ожидает обработки",
    color: "default",
  },
  extracting: {
    label: "Извлечение текста",
    color: "info",
  },
  extracted: {
    label: "Текст извлечён",
    color: "info",
  },
  sanitized: {
    label: "PII скрыты",
    color: "info",
  },
  structured: {
    label: "Структура построена",
    color: "info",
  },
  classified: {
    label: "Классификация выполнена",
    color: "info",
  },
  analyzing: {
    label: "Выполняются проверки",
    color: "info",
  },
  completed: {
    label: "Проверки выполнены",
    color: "success",
  },
  quarantine: {
    label: "Карантин (нужна проверка)",
    color: "warning",
  },
  failed: {
    label: "Ошибка обработки",
    color: "error",
  },
  duplicate: {
    label: "Дубликат",
    color: "default",
  },
  language_selection_required: {
    label: "Нужно выбрать язык",
    color: "warning",
    tooltip:
      "Загрузка документов завершена. Дальнейшая обработка для многоязычных документов остановлена до выбора основного языка проверки. По умолчанию выбран русский язык.",
    description:
      "Загрузка документов завершена. Для документов, в которых определено несколько языков, дальнейшая обработка — приведение к одноязычности по выбранному основному языку проверки, а также экстракция, санитизация, построение структуры, чанкинг и классификация — не будет продолжена, пока не выбран основной язык проверки. По умолчанию установлен русский язык.",
  },
};

/** Маппинг статуса Run в подпись и цвет. */
export const RUN_STATUS_CONFIG: Record<RunStatus, RunStatusConfig> = {
  pending: {
    label: "Ожидает запуска",
    color: "default",
  },
  running: {
    label: "Выполняется",
    color: "info",
  },
  completed: {
    label: "Завершён",
    color: "success",
  },
  completed_with_errors: {
    label: "Завершён с ошибками",
    color: "warning",
  },
  failed: {
    label: "Не удалось выполнить",
    color: "error",
  },
  cancelled: {
    label: "Отменён",
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
 */
export function getErrorStageLabel(
  details?: ProcessingErrorDetails | null,
): string {
  if (!details || !details.stage) {
    return "Неизвестная стадия";
  }
  return STAGE_LABELS[details.stage] ?? details.stage;
}


