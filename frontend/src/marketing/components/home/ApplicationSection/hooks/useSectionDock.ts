// src/marketing/components/home/ApplicationSection/hooks/useSectionDock.ts

import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

interface UseSectionDockOptions {
  enabled?: boolean;
  topOffset?: number;
  maxOvershootPx?: number;
  enterTopRatio?: number;
  minVisibleRatio?: number;
  cooldownMs?: number;
  behavior?: ScrollBehavior;
  minWidth?: number;
}

function getVisibleRatio(rect: DOMRect, viewportHeight: number): number {
  const visible = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);
  if (visible <= 0) return 0;
  return visible / Math.min(rect.height, viewportHeight);
}

export function useSectionDock(
  ref: RefObject<HTMLElement | null>,
  {
    enabled = true,
    topOffset = 0,
    maxOvershootPx = 180,
    enterTopRatio = 0.22,
    minVisibleRatio = 0.55,
    cooldownMs = 1200,
    behavior = 'smooth',
    minWidth = 1024,
  }: UseSectionDockOptions = {},
): void {
  const lastScrollYRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const cooldownTimeoutRef = useRef<number | null>(null);
  const isCoolingDownRef = useRef(false);
  const hasDockedInCurrentPassRef = useRef(false);

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return;

    const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
    if (isCoarsePointer || window.innerWidth < minWidth) return;

    lastScrollYRef.current = window.scrollY;

    const clearCooldown = () => {
      if (cooldownTimeoutRef.current !== null) {
        window.clearTimeout(cooldownTimeoutRef.current);
        cooldownTimeoutRef.current = null;
      }
      isCoolingDownRef.current = false;
    };

    const tryDock = () => {
      const el = ref.current;
      if (!el) return;

      const currentScrollY = window.scrollY;
      const isScrollingDown = currentScrollY > lastScrollYRef.current;
      lastScrollYRef.current = currentScrollY;

      const rect = el.getBoundingClientRect();
      const viewportHeight = window.innerHeight;

      // Если секция полностью вышла из viewport — разрешаем новый dock при следующем заходе
      if (rect.bottom <= 0 || rect.top >= viewportHeight) {
        hasDockedInCurrentPassRef.current = false;
        return;
      }

      if (!isScrollingDown || isCoolingDownRef.current || hasDockedInCurrentPassRef.current) {
        return;
      }

      const maxEnterTopPx = viewportHeight * enterTopRatio;
      const topIsNearViewportStart =
        rect.top >= -maxOvershootPx && rect.top <= maxEnterTopPx;

      if (!topIsNearViewportStart) return;

      const visibleRatio = getVisibleRatio(rect, viewportHeight);
      if (visibleRatio < minVisibleRatio) return;

      const targetTop = window.scrollY + rect.top - topOffset;
      const alreadyAligned = Math.abs(rect.top - topOffset) <= 2;

      if (alreadyAligned) {
        hasDockedInCurrentPassRef.current = true;
        return;
      }

      isCoolingDownRef.current = true;
      hasDockedInCurrentPassRef.current = true;

      window.scrollTo({
        top: Math.max(0, targetTop),
        behavior,
      });

      cooldownTimeoutRef.current = window.setTimeout(() => {
        isCoolingDownRef.current = false;
        cooldownTimeoutRef.current = null;
      }, cooldownMs);
    };

    const onScroll = () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
      }
      rafRef.current = window.requestAnimationFrame(tryDock);
    };

    window.addEventListener('scroll', onScroll, { passive: true });

    return () => {
      window.removeEventListener('scroll', onScroll);
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
      }
      clearCooldown();
    };
  }, [
    ref,
    enabled,
    topOffset,
    maxOvershootPx,
    enterTopRatio,
    minVisibleRatio,
    cooldownMs,
    behavior,
    minWidth,
  ]);
}


