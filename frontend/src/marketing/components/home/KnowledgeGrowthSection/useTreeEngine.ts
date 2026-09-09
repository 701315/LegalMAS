// src/marketing/components/home/KnowledgeGrowthSection/useTreeEngine.ts
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { pickFragmentForWidth } from "./contract-texts";
import type { Scanline, TreeLine } from "./types";

const SVG_URL = "/tree-mask.svg";
const SVG_WIDTH = 1280;
const SVG_HEIGHT = 1049;
const SCAN_STEP = 4;
const MIN_SEGMENT_WIDTH = 8;

type EngineState = {
  loading: boolean;
  error: string | null;
  lines: TreeLine[];
  svgText: string | null;
  width: number;
  height: number;
};

export function useTreeEngine(): EngineState {
  // 1. Инициализируем хук i18n для получения текущего языка
  const { i18n } = useTranslation("marketing");

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
        
        // 2. Передаем текущий язык в функцию генерации
        const lines = generateLines(scanlines, i18n.language);

        console.log(
          `🌳 Tree ready (${i18n.language}): ${lines.length} lines from ${scanlines.length} scanlines`
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
        console.error("🌳 Tree engine error:", e);
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
    // 3. Добавляем i18n.language в зависимости, чтобы дерево перестраивалось при смене языка
  }, [i18n.language]);

  return state;
}

async function rasterizeAndScan(svgText: string): Promise<Scanline[]> {
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

        const scanlines: Scanline[] = [];

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

// 4. Добавляем параметр lang в сигнатуру функции
function generateLines(scanlines: Scanline[], lang: string): TreeLine[] {
  const lines: TreeLine[] = [];

  scanlines.forEach((scanline, scanIndex) => {
    const heightRatio = scanline.y / SVG_HEIGHT;
    const isCanopy = heightRatio < 0.55;

    scanline.segments.forEach((segment, segIndex) => {
      const subSegments = splitSegmentIntoLeaves(segment, heightRatio);

      subSegments.forEach((sub, subIdx) => {
        const fontSize = isCanopy
          ? 11 + Math.random() * 3
          : 13 + Math.random() * 3;

        // 5. Передаем lang в функцию выбора фрагмента
        const fragment = pickFragmentForWidth(sub.width, fontSize, lang);

        let colorTone: TreeLine["colorTone"];
        if (fragment.isKey) {
          colorTone = "accent";
        } else {
          const r = Math.random();
          if (r < 0.6) colorTone = "primary";
          else colorTone = "muted";
        }

        const baseDelay = (1 - heightRatio) * 6000;
        const jitter = Math.random() * 500;

        lines.push({
          id: `tl-${scanIndex}-${segIndex}-${subIdx}`,
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

function splitSegmentIntoLeaves(
  segment: { xStart: number; xEnd: number; width: number },
  yRatio: number
): Array<{ xStart: number; width: number }> {
  const isCanopy = yRatio < 0.55;

  if (segment.width < 60) {
    return [{ xStart: segment.xStart, width: segment.width }];
  }

  if (isCanopy) {
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