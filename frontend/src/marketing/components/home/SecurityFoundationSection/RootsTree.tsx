// src/marketing/components/home/SecurityFoundationSection/RootsTree.tsx

import React, { useEffect, useRef, type RefObject } from "react";
import { useRootsEngine } from "./useRootsEngine";
import type { RootLine } from "./types";

// Замедлили: было FLIGHT_DURATION=1600, LAUNCH_INTERVAL=24
const FLIGHT_DURATION = 1200;
const LAUNCH_INTERVAL = 20;
const BATCH_SIZE = 10;

const SVG_URL = "/roots-mask.svg";

type Props = {
  active: boolean;
};

const RootsTree: React.FC<Props> = ({ active }) => {
  const { loading, error, lines, width, height } = useRootsEngine();
  const linesContainerRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (!active || loading || startedRef.current || lines.length === 0) return;
    if (!linesContainerRef.current) return;

    startedRef.current = true;
    runAnimation(linesContainerRef.current, rafRef, timeoutsRef);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      timeoutsRef.current.forEach((t) => clearTimeout(t));
      timeoutsRef.current = [];
    };
  }, [active, loading, lines]);

  const sortedLines = React.useMemo(() => {
    const sorted = [...lines].sort((a, b) => a.targetY - b.targetY);

    const stacks = 8;
    const buckets: RootLine[][] = Array.from({ length: stacks }, () => []);
    sorted.forEach((line, i) => {
      buckets[i % stacks].push(line);
    });

    const interleaved: RootLine[] = [];
    const maxLen = Math.max(...buckets.map((b) => b.length));
    for (let i = 0; i < maxLen; i++) {
      for (let s = 0; s < stacks; s++) {
        if (buckets[s][i]) interleaved.push(buckets[s][i]);
      }
    }

    return interleaved;
  }, [lines]);

  if (error) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <p className="text-sm text-red-500">Ошибка визуализации: {error}</p>
      </div>
    );
  }

  return (
    <div
      className="relative w-full"
      style={{
        aspectRatio: `${width} / ${height}`,
      }}
    >
      {/* Слой с корнями (text + mask) */}
      <div
        ref={linesContainerRef}
        className="absolute inset-0"
        style={{
          maskImage: `url(${SVG_URL})`,
          WebkitMaskImage: `url(${SVG_URL})`,
          maskSize: "100% 100%",
          WebkitMaskSize: "100% 100%",
          maskRepeat: "no-repeat",
          WebkitMaskRepeat: "no-repeat",
          maskPosition: "center",
          WebkitMaskPosition: "center",
          maskMode: "alpha",
        }}
      >
        {sortedLines.map((line, idx) => {
          const leftPct = (line.targetX / width) * 100;
          const topPct = (line.targetY / height) * 100;
          const widthPct = (line.width / width) * 100;

          return (
            <span
              key={line.id}
              data-idx={idx}
              data-target-top={topPct}
              data-target-opacity={line.opacity}
              data-key={line.isKey ? "true" : "false"}
              className="root-line"
              style={{
                position: "absolute",
                left: `${leftPct}%`,
                top: "-5%",
                maxWidth: `${widthPct}%`,
                fontFamily: "ui-monospace, 'IBM Plex Mono', monospace",
                fontWeight: 300,
                fontSize: `${line.fontSize}px`,
                whiteSpace: "nowrap",
                pointerEvents: "none",
                lineHeight: 1,
                letterSpacing: "-0.01em",
                opacity: 0,
                willChange: "top, opacity",
                color: getColorForTone(line.colorTone),
              }}
            >
              {line.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};

function getColorForTone(tone: RootLine["colorTone"]): string {
  switch (tone) {
    case "accent":
      return "rgba(15, 32, 24, 1)";
    case "primary":
      return "rgba(47, 90, 74, 0.95)";
    case "muted":
      return "rgba(63, 115, 95, 0.7)";
  }
}

function runAnimation(
  container: HTMLElement,
  rafRef: RefObject<number | null>,
  timeoutsRef: RefObject<ReturnType<typeof setTimeout>[]>
) {
  const elements = Array.from(
    container.querySelectorAll<HTMLElement>(".root-line")
  );

  type LineState = {
    el: HTMLElement;
    targetTop: number;
    targetOpacity: number;
    launchTime: number;
  };

  const states: LineState[] = elements.map((el, i) => {
    const batchIndex = Math.floor(i / BATCH_SIZE);
    const microJitter = Math.random() * (LAUNCH_INTERVAL * 0.8);
    return {
      el,
      targetTop: parseFloat(el.dataset.targetTop || "0"),
      targetOpacity: parseFloat(el.dataset.targetOpacity || "0.6"),
      launchTime: batchIndex * LAUNCH_INTERVAL + microJitter,
    };
  });

  const startTime = performance.now();

  function tick(now: number) {
    const elapsed = now - startTime;
    let allDone = true;

    for (const state of states) {
      const localElapsed = elapsed - state.launchTime;

      if (localElapsed < 0) {
        allDone = false;
        continue;
      }

      if (localElapsed >= FLIGHT_DURATION) {
        state.el.style.top = `${state.targetTop}%`;
        state.el.style.opacity = String(state.targetOpacity);
        continue;
      }

      allDone = false;
      const progress = localElapsed / FLIGHT_DURATION;
      const eased = easeOutCubic(progress);

      const currentTop = -5 + eased * (state.targetTop + 5);
      state.el.style.top = `${currentTop}%`;

      const opacity = Math.min(progress * 3, 1) * state.targetOpacity;
      state.el.style.opacity = String(opacity);
    }

    if (!allDone) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      states.forEach((s) => {
        s.el.style.top = `${s.targetTop}%`;
        s.el.style.opacity = String(s.targetOpacity);
      });

      // Игнорируем timeoutsRef — он не используется сейчас,
      // но оставлен в сигнатуре на случай добавления Meaning phase позже
      void timeoutsRef;
    }
  }

  rafRef.current = requestAnimationFrame(tick);
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export default RootsTree;