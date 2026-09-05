// =============================================================
// src/pages/tabs/overview/pipelineStepIcons.tsx
// Central registry of icons for pipeline steps.
//
// The same step.code must look visually identical across all UI locations:
//   - collapsed pipeline rail (narrow column)
//   - PipelineStepCard (expanded view)
//   - DomainCard (Documents card at the top)
//
// Therefore, the code → icon mapping is centralized here.
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
 * Map of step.code → Lucide icon component.
 *
 * Codes correspond to RunPipelineProgressResponse.steps[].code
 * from backend/src/api/schemas/runs.py.
 */
const STEP_ICON_BY_CODE: Record<string, LucideIcon> = {
  // Document preparation: convert → extract → pii
  document_preparation: FileSearch,

  // Document structure building
  structure_building: Layers,

  // Document / segment classification
  classification: Tags,

  // Semantic enrichment
  semantic_enrichment: Sparkles,

  // DD checks
  dd_checks: ShieldCheck,

  // Run finalization
  finalization: Flag,
};

/**
 * Get step icon by code.
 * Returns fallback (Cog) for unknown codes —
 * this protects UI from new step.codes without crashing.
 */
export function getPipelineStepIcon(code: string | undefined | null): LucideIcon {
  if (!code) return Cog;
  return STEP_ICON_BY_CODE[code] ?? Cog;
}

/**
 * Ready React component for step icon with forwarded props.
 */
export const PipelineStepIcon: React.FC<{
  code: string | undefined | null;
  className?: string;
  strokeWidth?: number;
}> = ({ code, className, strokeWidth = 2 }) => {
  const Icon = getPipelineStepIcon(code);
  return <Icon className={className} strokeWidth={strokeWidth} aria-hidden />;
};


