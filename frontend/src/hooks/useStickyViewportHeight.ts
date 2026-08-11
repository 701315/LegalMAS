// =============================================================
// src/hooks/useStickyViewportHeight.ts
//
// Хук возвращает точную высоту, которую sticky-элемент может
// занять внутри своего scroll-контейнера так, чтобы:
// - не выйти за нижнюю границу видимой области;
// - оставить визуальный отступ снизу (bottomOffset).
//
// Учитывает:
// - реальную позицию sticky-элемента относительно scroll-контейнера
// - текущий scroll offset
// - resize окна и родителей (ResizeObserver)
// - скролл (scroll event с requestAnimationFrame throttling)
//
// Универсально работает на любых layout'ах — не знает про header,
// paddings или магические константы.
// =============================================================

import { useEffect, useRef, useState } from "react";

export interface UseStickyViewportHeightOptions {
  /**
   * Дополнительный визуальный отступ снизу в пикселях.
   * По умолчанию 16px — стандартный gap проекта (соответствует p-4).
   */
  bottomOffset?: number;
}

/**
 * Находит ближайший scroll-контейнер вверх по дереву DOM.
 * Возвращает body если ничего не нашёл.
 */
function findScrollContainer(element: HTMLElement | null): HTMLElement {
  let current = element?.parentElement ?? null;

  while (current && current !== document.body) {
    const style = window.getComputedStyle(current);
    const overflowY = style.overflowY;

    if (overflowY === "auto" || overflowY === "scroll") {
      return current;
    }

    current = current.parentElement;
  }

  return document.body;
}

/**
 * Вычисляет offsetTop элемента относительно указанного контейнера.
 * Учитывает всю цепочку offsetParent'ов до тех пор, пока не
 * достигнет scroll-контейнера.
 */
function getOffsetTopWithinContainer(
  element: HTMLElement,
  container: HTMLElement,
): number {
  let offset = 0;
  let current: HTMLElement | null = element;

  while (current && current !== container) {
    offset += current.offsetTop;
    current = current.offsetParent as HTMLElement | null;

    if (!current || container.contains(current) === false) {
      break;
    }
  }

  return offset;
}

/**
 * Хук возвращает ref и вычисленную высоту в px для sticky-элемента.
 *
 * @param options.bottomOffset — визуальный отступ снизу (по умолчанию 16px)
 */
export function useStickyViewportHeight<T extends HTMLElement = HTMLDivElement>(
  options: UseStickyViewportHeightOptions = {},
): [React.RefObject<T | null>, number | null] {
  const { bottomOffset = 16 } = options;

  const elementRef = useRef<T>(null);
  const [height, setHeight] = useState<number | null>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const scrollContainer = findScrollContainer(element);
    let rafId: number | null = null;

    const measure = () => {
      if (rafId !== null) return;

      rafId = window.requestAnimationFrame(() => {
        rafId = null;

        if (!elementRef.current) return;

        const offsetTop = getOffsetTopWithinContainer(
          elementRef.current,
          scrollContainer,
        );

        const scrollTop = scrollContainer.scrollTop;
        const visibleTop = Math.max(0, offsetTop - scrollTop);
        const available = scrollContainer.clientHeight - visibleTop;

        const style = window.getComputedStyle(scrollContainer);
        const paddingBottom = parseFloat(style.paddingBottom) || 0;

        const finalHeight = Math.max(
          0,
          available - paddingBottom - bottomOffset,
        );

        setHeight(finalHeight > 0 ? finalHeight : null);
      });
    };

    measure();

    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(scrollContainer);
    if (element.parentElement) {
      resizeObserver.observe(element.parentElement);
    }

    window.addEventListener("resize", measure);
    scrollContainer.addEventListener("scroll", measure, { passive: true });

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", measure);
      scrollContainer.removeEventListener("scroll", measure);
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [bottomOffset]);

  return [elementRef, height];
}


