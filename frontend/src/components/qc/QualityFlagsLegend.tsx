// =============================================================
// src/components/qc/QualityFlagsLegend.tsx
// Легенда для значков флагов качества.
// =============================================================

import React from "react";

export const QualityFlagsLegend: React.FC = () => {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-600">
      <span className="font-semibold">Флаги качества:</span>
      <span className="flex items-center gap-1">
        <span className="w-2 h-2 rounded-full bg-orange-500" />
        <span>Структура документа нарушена</span>
      </span>
      <span className="flex items-center gap-1">
        <span className="w-2 h-2 rounded-full bg-purple-500" />
        <span>Использован LLM fallback</span>
      </span>
      <span className="flex items-center gap-1">
        <span className="w-2 h-2 rounded-full bg-gray-500" />
        <span>Другие флаги</span>
      </span>
    </div>
  );
};

export default QualityFlagsLegend;
