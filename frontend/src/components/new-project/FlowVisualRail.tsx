// =============================================================
// src/components/new-project/FlowVisualRail.tsx
//
// Третья колонка — визуал.
//
// Sticky-панель, автоматически подстраивающаяся под высоту
// scroll-контейнера с сохранением стандартного визуального
// отступа снизу.
// =============================================================

import React from "react";

import { useStickyViewportHeight } from "../../hooks/useStickyViewportHeight";

/**
 * Стандартный визуальный отступ снизу для sticky-панелей.
 * Совпадает с системным padding-4 (16px).
 */
const BOTTOM_OFFSET_PX = 16;

const FlowVisualRail: React.FC = () => {
  const [ref, height] = useStickyViewportHeight<HTMLDivElement>({
    bottomOffset: BOTTOM_OFFSET_PX,
  });

  return (
    <div
      ref={ref}
      className="sticky top-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] shadow-sm"
      style={height ? { height: `${height}px` } : undefined}
    >
      <img
        src="/newprojectpicture.png"
        alt="Запуск нового проекта"
        className="h-full w-full object-cover object-center"
      />
    </div>
  );
};

export default FlowVisualRail;


