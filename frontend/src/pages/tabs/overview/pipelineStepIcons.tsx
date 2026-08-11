// =============================================================
// src/pages/tabs/overview/pipelineStepIcons.tsx
// Единый реестр иконок для этапов pipeline.
//
// Один и тот же step.code должен визуально выглядеть одинаково
// во всех местах UI:
//   - collapsed pipeline rail (узкая колонка)
//   - PipelineStepCard (развёрнутый вид)
//   - DomainCard (карточка "Документы" сверху)
//
// Поэтому маппинг code → icon хранится централизованно здесь.
// =============================================================

import React from "react";
import {
  FileSearch,
  Layers,
  Tags,
  Sparkles,
  ShieldCheck,
  Flag,
  Cog,
  type LucideIcon,
} from "lucide-react";

/**
 * Карта step.code → Lucide icon component.
 *
 * Коды соответствуют RunPipelineProgressResponse.steps[].code
 * из backend/src/api/schemas/runs.py.
 */
const STEP_ICON_BY_CODE: Record<string, LucideIcon> = {
  // Подготовка документа: convert → extract → pii
  document_preparation: FileSearch,

  // Построение структуры документа
  structure_building: Layers,

  // Классификация документа / сегментов
  classification: Tags,

  // Семантическое обогащение
  semantic_enrichment: Sparkles,

  // DD-проверки
  dd_checks: ShieldCheck,

  // Финализация run
  finalization: Flag,
};

/**
 * Получить иконку этапа по коду.
 * Возвращает fallback (Cog), если код неизвестен —
 * это защищает UI от новых step.code без падения.
 */
export function getPipelineStepIcon(code: string | undefined | null): LucideIcon {
  if (!code) return Cog;
  return STEP_ICON_BY_CODE[code] ?? Cog;
}

/**
 * Готовый React-компонент иконки этапа с прокидываемыми props.
 */
export const PipelineStepIcon: React.FC<{
  code: string | undefined | null;
  className?: string;
  strokeWidth?: number;
}> = ({ code, className, strokeWidth = 2 }) => {
  const Icon = getPipelineStepIcon(code);
  return <Icon className={className} strokeWidth={strokeWidth} aria-hidden />;
};


