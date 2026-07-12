// src/marketing/components/platform/primitives/EditorialArrow.tsx

import React from "react";

/**
 * EditorialArrow — editorial-style «loop-arrow» ↳ для текстовых ссылок.
 *
 * Использование:
 *   • На текстовых ссылках «Подробнее / Learn More» — вместо стандартной →
 *   • НЕ используется на CTA-кнопках — там остаётся lucide ArrowRight
 *
 * Композиция как inline-SVG для полного контроля стиля.
 * Наследует currentColor от родителя (сам меняет цвет от контекста).
 *
 * Пример:
 *   <a className="cta-link">
 *     Подробнее <EditorialArrow />
 *   </a>
 */

interface EditorialArrowProps {
  size?: number;
  className?: string;
}

const EditorialArrow: React.FC<EditorialArrowProps> = ({
  size = 12,
  className,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      className={className}
      aria-hidden="true"
      style={{ display: "inline-block", verticalAlign: "baseline" }}
    >
      {/* Вертикальная часть — идёт сверху вниз */}
      <path
        d="M 3 1 L 3 7"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
      {/* Горизонтальная часть с загибом внизу */}
      <path
        d="M 3 7 L 10 7"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
      {/* Стрелка на конце */}
      <path
        d="M 8 5 L 10 7 L 8 9"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
};

export default EditorialArrow;


