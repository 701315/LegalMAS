// src/marketing/components/platform/primitives/PathCrumb.tsx

import React from "react";

/**
 * PathCrumb — editorial-style path-крошка в стиле Legora (PRODUCT / Tabular Review).
 *
 * Композиция:
 *   • root часть (например, «ПЛАТФОРМА») — приглушённая
 *   • слэш — ещё более приглушённый
 *   • leaf часть (например, «Анализ документов») — основной цвет
 *
 * Типографика — uppercase, tracking-широкий, малый размер (11px).
 * Используется как замена простому eyebrow на product-страницах.
 *
 * Пример:
 *   <PathCrumb root="ПЛАТФОРМА" leaf="Анализ документов" />
 */

interface PathCrumbProps {
  root: string;
  leaf: string;
  /**
   * Вариант цвета для тёмных секций (белый текст).
   * По умолчанию — светлая тема.
   */
  variant?: "light" | "dark";
}

const PathCrumb: React.FC<PathCrumbProps> = ({ root, leaf, variant = "light" }) => {
  const rootColor = variant === "dark" ? "rgba(250, 248, 245, 0.45)" : "#A8A29E";
  const slashColor = variant === "dark" ? "rgba(250, 248, 245, 0.28)" : "#D6D0C7";
  const leafColor = variant === "dark" ? "#FAF8F5" : "#1A1917";

  return (
    <div
      className="inline-flex items-baseline gap-2 text-[11px] font-medium uppercase tracking-[0.22em]"
      aria-label={`${root} / ${leaf}`}
    >
      <span style={{ color: rootColor }}>{root}</span>
      <span style={{ color: slashColor }} aria-hidden="true">
        /
      </span>
      <span style={{ color: leafColor }}>{leaf}</span>
    </div>
  );
};

export default PathCrumb;



