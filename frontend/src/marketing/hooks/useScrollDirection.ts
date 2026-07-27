// src/marketing/hooks/useScrollDirection.ts
//
// Hook реализует паттерн "hide on scroll down, show on scroll up",
// используемый в современных мобильных лендингах (Medium, YouTube, Instagram).
//
// Оптимизации:
//   - Scroll handler throttled через requestAnimationFrame (макс. 1 вызов на кадр)
//   - Пороговое значение (threshold) фильтрует микро-движения
//   - Верхняя зона (alwaysVisibleAbove) — header всегда виден рядом с топом
//   - Можно отключить через enabled=false (для desktop)

import { useEffect, useRef, useState } from "react";

export interface UseScrollDirectionOptions {
  /**
   * Минимальное смещение (px) для срабатывания смены направления.
   * Фильтрует дрожание пальца и микро-инерцию.
   * @default 4
   */
  threshold?: number;

  /**
   * Header всегда виден, если scrollY меньше этого значения.
   * @default 80
   */
  alwaysVisibleAbove?: number;

  /**
   * Включена ли логика hide/show. Если false — hidden всегда false.
   * @default true
   */
  enabled?: boolean;
}

/**
 * @returns hidden — true если header нужно скрыть (scroll down),
 *                   false если показать (scroll up или у верха)
 */
export function useScrollDirection(
  options: UseScrollDirectionOptions = {}
): boolean {
  const {
    threshold = 4,
    alwaysVisibleAbove = 80,
    enabled = true,
  } = options;

  const [hidden, setHidden] = useState(false);
  const lastYRef = useRef(0);
  const tickingRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setHidden(false);
      return;
    }

    // Инициализация lastY от текущей позиции — избегает "прыжка"
    // при монтировании компонента, если пользователь уже прокрутил.
    lastYRef.current = window.scrollY;

    const update = () => {
      const currentY = window.scrollY;
      const diff = currentY - lastYRef.current;

      if (currentY < alwaysVisibleAbove) {
        setHidden(false);
      } else if (diff > threshold) {
        setHidden(true);
      } else if (diff < -threshold) {
        setHidden(false);
      }

      lastYRef.current = currentY;
      tickingRef.current = false;
    };

    const onScroll = () => {
      if (tickingRef.current) return;
      tickingRef.current = true;
      window.requestAnimationFrame(update);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold, alwaysVisibleAbove, enabled]);

  return hidden;
}


