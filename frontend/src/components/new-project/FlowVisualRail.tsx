// =============================================================
// src/components/new-project/FlowVisualRail.tsx
//
// 25% колонка — визуал во весь блок без внутренних отступов.
// Sticky.
// =============================================================

import React from "react";

const FlowVisualRail: React.FC = () => {
  return (
    <aside className="sticky top-4">
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] shadow-sm">
        <img
          src="/newprojectpicture.png"
          alt="Запуск нового проекта"
          className="w-full h-full object-cover"
        />
      </div>
    </aside>
  );
};

export default FlowVisualRail;


