// src/marketing/hooks/useMediaQuery.ts
//
// Реактивный hook для отслеживания CSS media queries через нативный
// window.matchMedia API. В отличие от подходов на основе window.innerWidth
// + resize listener, matchMedia:
//   - реагирует только на пересечение брейкпоинта (меньше событий)
//   - работает нативно на уровне браузера
//   - совпадает 1-в-1 с CSS media queries
//
// SSR-safe: возвращает false при отсутствии window.

import { useEffect, useState } from "react";

/**
 * Возвращает true, если текущий viewport соответствует переданной media query.
 *
 * @example
 *   const isMobile = useMediaQuery("(max-width: 1023px)");
 *   const isDark   = useMediaQuery("(prefers-color-scheme: dark)");
 */
export function useMediaQuery(query: string): boolean {
  const getMatch = (): boolean => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  };

  const [matches, setMatches] = useState<boolean>(getMatch);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mql = window.matchMedia(query);

    // Синхронизируем состояние — на случай, если query изменился
    setMatches(mql.matches);

    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    // Modern API (Safari 14+, все актуальные браузеры)
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}



