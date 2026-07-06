// src/marketing/components/home/KnowledgeGrowthSection/KnowledgeTree.tsx
import React, { useEffect, useRef, type RefObject } from "react";
import { useTreeEngine } from "./useTreeEngine";
import type { TreeLine } from "./types";

const FLIGHT_DURATION = 1100;
const LAUNCH_INTERVAL = 24;
const MEANING_DELAY = 1200;

const SVG_URL = "/tree-mask.svg";

type Props = {
  active: boolean;
};

const KnowledgeTree: React.FC<Props> = ({ active }) => {
  const { loading, error, lines, width, height } = useTreeEngine();
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
    const buckets: TreeLine[][] = Array.from({ length: stacks }, () => []);
    sorted.forEach((line, i) => {
      buckets[i % stacks].push(line);
    });

    const interleaved: TreeLine[] = [];
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
              className="tree-line"
              style={{
                position: "absolute",
                left: `${leftPct}%`,
                top: "100%",
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

      <style>{`
        .tree-line.is-highlighted {
          text-shadow: 0 0 8px rgba(200, 107, 82, 0.45);
          color: rgb(200, 107, 82) !important;
          transition: text-shadow 800ms ease, color 800ms ease;
        }
      `}</style>
    </div>
  );
};

function getColorForTone(tone: TreeLine["colorTone"]): string {
  switch (tone) {
    case "accent":
      return "rgba(200, 107, 82, 0.85)"; // terracotta
    case "primary":
      return "rgba(26, 25, 23, 0.55)"; // warm dark
    case "muted":
      return "rgba(168, 162, 158, 0.5)"; // warm gray
  }
}

function runAnimation(
  container: HTMLElement,
  rafRef: RefObject<number | null>,
  timeoutsRef: RefObject<ReturnType<typeof setTimeout>[]>
) {
  const elements = Array.from(
    container.querySelectorAll<HTMLElement>(".tree-line")
  );

  type LineState = {
    el: HTMLElement;
    targetTop: number;
    targetOpacity: number;
    launchTime: number;
  };

  const BATCH_SIZE = 10;

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

      const currentTop = 100 - eased * (100 - state.targetTop);
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

      const t = setTimeout(() => {
        const keyElements = elements.filter((el) => el.dataset.key === "true");
        const shuffled = [...keyElements].sort(() => Math.random() - 0.5);
        const toHighlight = shuffled.slice(0, Math.min(8, shuffled.length));

        toHighlight.forEach((el, i) => {
          const t2 = setTimeout(() => {
            el.classList.add("is-highlighted");
            const t3 = setTimeout(
              () => el.classList.remove("is-highlighted"),
              2200
            );
            timeoutsRef.current?.push(t3);
          }, i * 550);
          timeoutsRef.current?.push(t2);
        });
      }, MEANING_DELAY);
      timeoutsRef.current?.push(t);
    }
  }

  rafRef.current = requestAnimationFrame(tick);
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export default KnowledgeTree;


