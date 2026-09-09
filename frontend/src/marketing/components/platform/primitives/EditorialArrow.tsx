import React from "react";
import { useTranslation } from "react-i18next";

/**
 * EditorialArrow — editorial-style «loop-arrow» ↳ для текстовых ссылок.
 *
 * Использование:
 *   • На текстовых ссылках «Подробнее / Learn More» — вместо стандартной →
 *   • НЕ используется на CTA-кнопках — там остаётся lucide ArrowRight
 *
 * Композиция как inline-SVG для полного контроля стиля.
 * Наследует currentColor от родителя (сам меняет цвет от контекста).
 */

interface EditorialArrowProps {
  size?: number;
  className?: string;
}

const EditorialArrow: React.FC<EditorialArrowProps> = ({
  size = 12,
  className,
}) => {
  // RTL FIX: Инициализация i18n для определения направления письма
  const { i18n } = useTranslation();
  const isRTL = i18n.language === "ar";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      className={className}
      aria-hidden="true"
      // RTL FIX: Зеркалирование стрелки для арабского языка (указывает влево-вниз)
      style={{
        display: "inline-block",
        verticalAlign: "baseline",
        transform: isRTL ? "scaleX(-1)" : "none",
        transition: "transform 0.2s ease", // Плавность при смене языка
      }}
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