// src/components/marketing/landing/ApplicationSection/hooks/useIntersection.ts

import { useState, useEffect } from 'react';
import type { RefObject } from 'react';

export function useIntersection(
  ref: RefObject<HTMLElement | null>,
  threshold: number = 0.3,
): boolean {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => setIsVisible(entry.isIntersecting),
      { threshold },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, threshold]);

  return isVisible;
}

