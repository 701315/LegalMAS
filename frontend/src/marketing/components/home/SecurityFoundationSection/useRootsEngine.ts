// src/components/marketing/landing/SecurityFoundationSection/useRootsEngine.ts

import { useEffect, useState } from "react";
import { pickFragmentForWidth } from "./infrastructure-texts";
import type { RootScanline, RootLine } from "./types";

const SVG_URL = "/roots-mask.svg";

// Размеры исходного SVG (новые корни 1402×1122)
const SVG_WIDTH = 1402;
const SVG_HEIGHT = 1122;

// Параметры синхронизированы с деревом (useTreeEngine.ts)
const SCAN_STEP = 8;
const MIN_SEGMENT_WIDTH = 18;

type EngineState = {
  loading: boolean;
  error: string | null;
  lines: RootLine[];
  svgText: string | null;
  width: number;
  height: number;
};

export function useRootsEngine(): EngineState {
  const [state, setState] = useState<EngineState>({
    loading: true,
    error: null,
    lines: [],
    svgText: null,
    width: SVG_WIDTH,
    height: SVG_HEIGHT,
  });

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        const res = await fetch(SVG_URL);
        if (!res.ok) throw new Error(`Failed to load SVG: ${res.status}`);
        const svgText = await res.text();

        const scanlines = await rasterizeAndScan(svgText);
        const lines = generateLines(scanlines);

        console.log(
          `🌱 Roots ready: ${lines.length} lines from ${scanlines.length} scanlines`
        );

        if (!cancelled) {
          setState({
            loading: false,
            error: null,
            lines,
            svgText,
            width: SVG_WIDTH,
            height: SVG_HEIGHT,
          });
        }
      } catch (e: unknown) {
        console.error("🌱 Roots engine error:", e);
        if (!cancelled) {
          const message = e instanceof Error ? e.message : "Unknown error";
          setState((s) => ({ ...s, loading: false, error: message }));
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

async function rasterizeAndScan(svgText: string): Promise<RootScanline[]> {
  return new Promise((resolve, reject) => {
    const encoded = encodeURIComponent(svgText);
    const dataUrl = `data:image/svg+xml;charset=utf-8,${encoded}`;

    const img = new Image();

    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = SVG_WIDTH;
        canvas.height = SVG_HEIGHT;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("No canvas context");

        ctx.fillStyle = "white";
        ctx.fillRect(0, 0, SVG_WIDTH, SVG_HEIGHT);
        ctx.drawImage(img, 0, 0, SVG_WIDTH, SVG_HEIGHT);

        const imageData = ctx.getImageData(0, 0, SVG_WIDTH, SVG_HEIGHT).data;

        const scanlines: RootScanline[] = [];

        for (let y = 0; y < SVG_HEIGHT; y += SCAN_STEP) {
          const segments = [];
          let inSegment = false;
          let segmentStart = 0;

          for (let x = 0; x < SVG_WIDTH; x++) {
            const idx = (y * SVG_WIDTH + x) * 4;
            const r = imageData[idx];
            const g = imageData[idx + 1];
            const b = imageData[idx + 2];
            const isFilled = r < 128 && g < 128 && b < 128;

            if (isFilled && !inSegment) {
              segmentStart = x;
              inSegment = true;
            } else if (!isFilled && inSegment) {
              if (x - segmentStart >= MIN_SEGMENT_WIDTH) {
                segments.push({
                  xStart: segmentStart,
                  xEnd: x,
                  width: x - segmentStart,
                });
              }
              inSegment = false;
            }
          }

          if (inSegment && SVG_WIDTH - segmentStart >= MIN_SEGMENT_WIDTH) {
            segments.push({
              xStart: segmentStart,
              xEnd: SVG_WIDTH,
              width: SVG_WIDTH - segmentStart,
            });
          }

          if (segments.length > 0) {
            scanlines.push({ y, segments });
          }
        }

        resolve(scanlines);
      } catch (err) {
        reject(err);
      }
    };

    img.onerror = () => reject(new Error("SVG image failed to load"));
    img.src = dataUrl;
  });
}

function generateLines(scanlines: RootScanline[]): RootLine[] {
  const lines: RootLine[] = [];

  scanlines.forEach((scanline, scanIndex) => {
    const heightRatio = scanline.y / SVG_HEIGHT;
    // В корнях наоборот: "верх" (heightRatio < 0.45) это основание (как ствол),
    // "низ" (heightRatio > 0.45) это глубина (как крона по плотности нарезки)
    const isDeep = heightRatio > 0.45;

    scanline.segments.forEach((segment, segIndex) => {
      const subSegments = splitSegmentIntoRoots(segment, heightRatio);

      subSegments.forEach((sub, subIdx) => {
        // СИНХРОНИЗАЦИЯ С ДЕРЕВОМ:
        // — глубокие корни (тонкие) = крона дерева = 11-14px
        // — основание корней (толстое) = ствол дерева = 13-16px
        const fontSize = isDeep
          ? 11 + Math.random() * 3 // 11-14px (как крона)
          : 13 + Math.random() * 3; // 13-16px (как ствол)

        const fragment = pickFragmentForWidth(sub.width, fontSize);

        let colorTone: RootLine["colorTone"];
        if (fragment.isKey) {
          colorTone = "accent";
        } else {
          const r = Math.random();
          if (r < 0.6) colorTone = "primary";
          else colorTone = "muted";
        }

        // СИНХРОНИЗАЦИЯ С ДЕРЕВОМ: opacity 0.5 + random * 0.4
        const baseDelay = heightRatio * 6000;
        const jitter = Math.random() * 500;

        lines.push({
          id: `rl-${scanIndex}-${segIndex}-${subIdx}`,
          text: fragment.text,
          clauseType: fragment.type,
          isKey: fragment.isKey,
          targetX: sub.xStart,
          targetY: scanline.y,
          width: sub.width,
          fontSize,
          opacity: 0.5 + Math.random() * 0.4,
          delay: baseDelay + jitter,
          colorTone,
        });
      });
    });
  });

  return lines;
}

/**
 * Нарезка сегментов корня — синхронизирована с splitSegmentIntoLeaves дерева.
 * В глубоких корнях (как крона) — режем агрессивнее.
 * У основания (как ствол) — крупные читаемые фрагменты.
 */
function splitSegmentIntoRoots(
  segment: { xStart: number; xEnd: number; width: number },
  yRatio: number
): Array<{ xStart: number; width: number }> {
  const isDeep = yRatio > 0.45;

  if (segment.width < 60) {
    return [{ xStart: segment.xStart, width: segment.width }];
  }

  // ─── ГЛУБОКИЕ КОРНИ (как крона дерева) ───
  if (isDeep) {
    if (segment.width < 90) {
      const cut = segment.width * (0.45 + Math.random() * 0.15);
      const gap = 2 + Math.random() * 3;
      return [
        { xStart: segment.xStart, width: cut - gap / 2 },
        {
          xStart: segment.xStart + cut + gap / 2,
          width: segment.width - cut - gap / 2,
        },
      ];
    }
    if (segment.width < 180) {
      return splitIntoParts(segment, 3);
    }
    const parts = 4 + Math.floor(Math.random() * 2);
    return splitIntoParts(segment, parts);
  }

  // ─── ОСНОВАНИЕ КОРНЕЙ (как ствол дерева) ───
  if (segment.width < 100) {
    return [{ xStart: segment.xStart, width: segment.width }];
  }
  if (segment.width < 200) {
    const cut = segment.width * (0.4 + Math.random() * 0.2);
    const gap = 4 + Math.random() * 6;
    return [
      { xStart: segment.xStart, width: cut - gap / 2 },
      {
        xStart: segment.xStart + cut + gap / 2,
        width: segment.width - cut - gap / 2,
      },
    ];
  }
  return splitIntoParts(segment, 2);
}

function splitIntoParts(
  segment: { xStart: number; xEnd: number; width: number },
  parts: number
): Array<{ xStart: number; width: number }> {
  const result: Array<{ xStart: number; width: number }> = [];
  const baseW = segment.width / parts;
  let cursor = segment.xStart;

  for (let i = 0; i < parts; i++) {
    const variance = baseW * (0.7 + Math.random() * 0.45);
    const remaining = segment.xEnd - cursor;
    const w = Math.min(variance, remaining - 6);
    if (w < 14) break;
    result.push({ xStart: cursor, width: w });
    const gap = 3 + Math.random() * 6;
    cursor += w + gap;
    if (cursor >= segment.xEnd - 12) break;
  }

  return result;
}

