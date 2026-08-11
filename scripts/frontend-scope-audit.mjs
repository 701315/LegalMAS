#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const SRC_ROOT = path.resolve(
  process.argv[2] ?? "/srv/steloom-dev/frontend/src",
);
const OUT_PREFIX = path.resolve(
  process.argv[3] ?? "/srv/steloom-dev/scripts/frontend-scope-report",
);

const SCAN_EXTENSIONS = new Set([".ts", ".tsx", ".css"]);
const IGNORE_DIRS = new Set([
  "marketing",
  "node_modules",
  "dist",
  ".git",
  "__tests__",
]);

const MAX_HITS_PER_RULE = 5;

function normalizePath(value) {
  return value.split(path.sep).join("/");
}

function isIgnoredRelativePath(relPath) {
  const normalized = normalizePath(relPath);

  if (!normalized) {
    return false;
  }

  const parts = normalized.split("/");

  if (parts.some((part) => IGNORE_DIRS.has(part))) {
    return true;
  }

  if (normalized.endsWith(".d.ts")) {
    return true;
  }

  if (/\.(test|spec)\.(ts|tsx|js|jsx)$/.test(normalized)) {
    return true;
  }

  return false;
}

async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const absPath = path.join(dir, entry.name);
    const relPath = normalizePath(path.relative(SRC_ROOT, absPath));

    if (isIgnoredRelativePath(relPath)) {
      continue;
    }

    if (entry.isDirectory()) {
      files.push(...(await walk(absPath)));
      continue;
    }

    const ext = path.extname(entry.name);
    if (SCAN_EXTENSIONS.has(ext)) {
      files.push(absPath);
    }
  }

  return files;
}

function countRegexMatchesInText(text, regex) {
  const safeRegex = new RegExp(regex.source, regex.flags.includes("g") ? regex.flags : `${regex.flags}g`);
  const matches = text.match(safeRegex);
  return matches ? matches.length : 0;
}

function collectLineHits(lines, regex, maxHits = MAX_HITS_PER_RULE) {
  const hits = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const safeRegex = new RegExp(regex.source, regex.flags.replace(/g/g, ""));
    if (safeRegex.test(line)) {
      hits.push({
        line: index + 1,
        text: line.trim().slice(0, 240),
      });
    }

    if (hits.length >= maxHits) {
      break;
    }
  }

  return hits;
}

const PATH_RULES = [
  {
    id: "ROOT_APP",
    weight: 40,
    when: (relPath) => relPath === "App.tsx",
    reason: "Корневой routing/layout файл приложения",
  },
  {
    id: "GLOBAL_CSS",
    weight: 35,
    when: (relPath) => relPath === "index.css" || relPath === "App.css",
    reason: "Глобальные стили, влияющие на весь app",
  },
  {
    id: "APP_LAYOUT",
    weight: 40,
    when: (relPath) => relPath.startsWith("components/layout/"),
    reason: "Core layout / AppShell слой",
  },
  {
    id: "AUTH_LAYER",
    weight: 16,
    when: (relPath) => relPath.startsWith("components/auth/"),
    reason: "Auth / route guard слой",
  },
  {
    id: "PAGE_ENTRY",
    weight: 18,
    when: (relPath) =>
      relPath.startsWith("pages/") && relPath.endsWith(".tsx"),
    reason: "Страничный app-компонент",
  },
  {
    id: "TAB_SCREEN",
    weight: 18,
    when: (relPath) => relPath.includes("/tabs/"),
    reason: "Tab/workspace screen",
  },
  {
    id: "DATA_HEAVY_NAME",
    weight: 12,
    when: (relPath) =>
      /(Grid|Table|Admin|Instruction|Playbook|Overview|Evidence|Document|Viewer|Panel)\.tsx$/.test(
        relPath,
      ),
    reason: "По имени похож на data-heavy / admin / workspace файл",
  },
];

const CONTENT_RULES = [
  {
    id: "ROUTE_HEAVY",
    reason: "Много route-объявлений в одном файле",
    evaluate: (text) => {
      const count = countRegexMatchesInText(text, /<Route\b/g);
      if (count < 6) {
        return null;
      }

      return {
        count,
        weight: 12 + Math.min(12, count),
        hits: [],
      };
    },
  },
  {
    id: "OVERFLOW_HIDDEN",
    reason: "Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership",
    evaluate: (text, lines) => {
      const regex = /\boverflow-hidden\b|overflow(?:-x|-y)?\s*:\s*hidden\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 8 + Math.min(8, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "VIEWPORT_CONTRACT",
    reason: "Есть viewport-bound высота (h-screen / dvh / 100vh / min-h-screen) — важно для shell/mobile",
    evaluate: (text, lines) => {
      const regex = /\bh-screen\b|\bh-\[100dvh\]\b|\bmin-h-screen\b|\b100vh\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 8 + Math.min(4, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "INLINE_SIZE_STYLE",
    reason: "Есть inline style с width/height/min/max — проверить необходимость",
    evaluate: (text, lines) => {
      const regex =
        /style=\{\{[^}]*\b(width|minWidth|maxWidth|height|minHeight|maxHeight)\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 14 + Math.min(6, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "DENSE_GRID",
    reason: "Есть grid-cols-3+ — проверить mobile-first дисциплину",
    evaluate: (text, lines) => {
      const regex = /\bgrid-cols-(3|4|5|6|7|8|9|10|11|12)\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 10 + Math.min(6, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "LOCAL_X_SCROLL",
    reason: "Есть локальный horizontal scroll — вероятно data-heavy surface",
    evaluate: (text, lines) => {
      const regex = /\boverflow-x-auto\b|\boverflow-x-scroll\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 8 + Math.min(4, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "TABLE_OR_GRID",
    reason: "Есть таблица / grid / AG Grid — проверить adaptive behavior",
    evaluate: (text, lines, relPath) => {
      const regex = /<table\b|AgGridReact|ag-grid|DDGrid|DD Grid|grid-template-columns/i;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      const nameBoost =
        /(Grid|Table)\.tsx$/.test(relPath) || relPath.includes("/tabs/Grid")
          ? 1
          : 0;

      if (count === 0 && nameBoost === 0) {
        return null;
      }

      return {
        count: count + nameBoost,
        weight: 12 + Math.min(6, count + nameBoost),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "FIXED_PX_UTILITY",
    reason: "Есть arbitrary px utility — проверить, не ломает ли responsive layout",
    evaluate: (text, lines) => {
      const regex = /\b(?:w|h|min-w|max-w|min-h|max-h)-\[\d+px\]/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 6 + Math.min(4, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "BREAKPOINT_VISIBILITY",
    reason: "Есть breakpoint-driven visibility/layout logic — важен responsive audit",
    evaluate: (text, lines) => {
      const regex = /\b(?:sm|md|lg|xl|2xl):(hidden|flex|block|grid|inline-flex)\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 8 + Math.min(8, Math.floor(count / 2)),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "DIALOG_MODAL",
    reason: "Есть dialog/modal/drawer поведение — важно для accessibility и layering",
    evaluate: (text, lines) => {
      const regex = /\brole="dialog"\b|\baria-modal="true"\b|\bDialog\b|\bdrawer\b/i;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 6 + Math.min(4, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "TAB_NAV",
    reason: "Есть tabs/tablist — важно для mobile nav и keyboard behavior",
    evaluate: (text, lines) => {
      const regex = /\brole="tablist"\b|\brole="tab"\b|\baria-selected\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 8 + Math.min(4, count),
        hits: collectLineHits(lines, regex),
      };
    },
  },
  {
    id: "FULL_HEIGHT_LAYOUT",
    reason: "Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout",
    evaluate: (text, lines) => {
      const regex = /\bmin-h-0\b|\bmin-w-0\b|\bh-full\b/;
      const count = lines.filter((line) =>
        new RegExp(regex.source, regex.flags).test(line),
      ).length;

      if (count === 0) {
        return null;
      }

      return {
        count,
        weight: 4 + Math.min(6, Math.floor(count / 2)),
        hits: collectLineHits(lines, regex),
      };
    },
  },
];

function bucketFromScore(score) {
  if (score >= 80) return "must_audit";
  if (score >= 45) return "should_audit";
  if (score >= 20) return "watchlist";
  return "low";
}

function primaryAreaForPath(relPath) {
  if (relPath === "App.tsx") return "routing";
  if (relPath === "index.css" || relPath === "App.css") return "global-styles";
  if (relPath.startsWith("components/layout/")) return "layout";
  if (relPath.startsWith("components/auth/")) return "auth";
  if (relPath.startsWith("pages/")) return "pages";
  if (relPath.startsWith("components/")) return "components";
  if (relPath.startsWith("hooks/")) return "hooks";
  return "other";
}

async function analyzeFile(absPath) {
  const relPath = normalizePath(path.relative(SRC_ROOT, absPath));
  const text = await fs.readFile(absPath, "utf8");
  const lines = text.split(/\r?\n/);

  const findings = [];
  let score = 0;

  for (const rule of PATH_RULES) {
    if (rule.when(relPath, text, lines)) {
      score += rule.weight;
      findings.push({
        id: rule.id,
        reason: rule.reason,
        weight: rule.weight,
        count: 1,
        hits: [],
      });
    }
  }

  for (const rule of CONTENT_RULES) {
    const result = rule.evaluate(text, lines, relPath);
    if (!result) {
      continue;
    }

    score += result.weight;
    findings.push({
      id: rule.id,
      reason: rule.reason,
      weight: result.weight,
      count: result.count,
      hits: result.hits,
    });
  }

  const bucket = bucketFromScore(score);

  return {
    path: relPath,
    area: primaryAreaForPath(relPath),
    ext: path.extname(relPath),
    lines: lines.length,
    score,
    bucket,
    findings,
  };
}

function buildMarkdownReport({
  srcRoot,
  scannedAt,
  scannedFilesCount,
  report,
}) {
  const bucketSummary = report.reduce(
    (acc, item) => {
      acc[item.bucket] = (acc[item.bucket] ?? 0) + 1;
      return acc;
    },
    { must_audit: 0, should_audit: 0, watchlist: 0, low: 0 },
  );

  const topQueue = report.filter((item) => item.bucket !== "low").slice(0, 50);

  const lines = [];
  lines.push("# Frontend scope audit");
  lines.push("");
  lines.push(`- Source root: \`${srcRoot}\``);
  lines.push("- Excluded: `src/marketing`, `__tests__`, `*.test.*`, `*.spec.*`, `*.d.ts`");
  lines.push(`- Scanned at: ${scannedAt}`);
  lines.push(`- Scanned files: ${scannedFilesCount}`);
  lines.push("");
  lines.push("## Priority summary");
  lines.push("");
  lines.push(`- must_audit: **${bucketSummary.must_audit}**`);
  lines.push(`- should_audit: **${bucketSummary.should_audit}**`);
  lines.push(`- watchlist: **${bucketSummary.watchlist}**`);
  lines.push(`- low: **${bucketSummary.low}**`);
  lines.push("");
  lines.push("## Top review queue");
  lines.push("");
  lines.push("| Score | Bucket | Area | File |");
  lines.push("|---:|---|---|---|");

  for (const item of topQueue) {
    lines.push(`| ${item.score} | ${item.bucket} | ${item.area} | \`${item.path}\` |`);
  }

  lines.push("");
  lines.push("## Detailed findings");
  lines.push("");

  for (const item of topQueue) {
    lines.push(`### ${item.path}`);
    lines.push("");
    lines.push(`- score: **${item.score}**`);
    lines.push(`- bucket: **${item.bucket}**`);
    lines.push(`- area: **${item.area}**`);
    lines.push(`- lines: **${item.lines}**`);
    lines.push("");

    for (const finding of item.findings) {
      lines.push(`- [${finding.id}] ${finding.reason} (weight: ${finding.weight}, count: ${finding.count})`);
      if (finding.hits.length > 0) {
        for (const hit of finding.hits) {
          lines.push(`  - L${hit.line}: \`${hit.text.replace(/`/g, "'")}\``);
        }
      }
    }

    lines.push("");
  }

  return lines.join("\n");
}

async function main() {
  const files = await walk(SRC_ROOT);
  const analyzed = await Promise.all(files.map(analyzeFile));

  analyzed.sort((a, b) => {
    if (b.score !== a.score) {
      return b.score - a.score;
    }

    return a.path.localeCompare(b.path);
  });

  const scannedAt = new Date().toISOString();

  const jsonReport = {
    srcRoot: SRC_ROOT,
    excluded: [
      "src/marketing",
      "__tests__",
      "*.test.*",
      "*.spec.*",
      "*.d.ts",
    ],
    scannedAt,
    scannedFilesCount: analyzed.length,
    report: analyzed,
  };

  const markdownReport = buildMarkdownReport({
    srcRoot: SRC_ROOT,
    scannedAt,
    scannedFilesCount: analyzed.length,
    report: analyzed,
  });

  await fs.writeFile(`${OUT_PREFIX}.json`, JSON.stringify(jsonReport, null, 2));
  await fs.writeFile(`${OUT_PREFIX}.md`, markdownReport, "utf8");

  const summary = analyzed.reduce(
    (acc, item) => {
      acc[item.bucket] = (acc[item.bucket] ?? 0) + 1;
      return acc;
    },
    { must_audit: 0, should_audit: 0, watchlist: 0, low: 0 },
  );

  console.log("");
  console.log("Frontend scope audit completed.");
  console.log(`Source: ${SRC_ROOT}`);
  console.log(`Scanned files: ${analyzed.length}`);
  console.log("");
  console.log("Priority summary:");
  console.log(`  must_audit:  ${summary.must_audit}`);
  console.log(`  should_audit:${summary.should_audit}`);
  console.log(`  watchlist:   ${summary.watchlist}`);
  console.log(`  low:         ${summary.low}`);
  console.log("");
  console.log(`JSON report: ${OUT_PREFIX}.json`);
  console.log(`MD report:   ${OUT_PREFIX}.md`);
  console.log("");
  console.log("Top 20 files:");
  analyzed.slice(0, 20).forEach((item, index) => {
    console.log(
      `${String(index + 1).padStart(2, " ")}. [${item.score}] ${item.bucket} :: ${item.path}`,
    );
  });
  console.log("");
}

main().catch((error) => {
  console.error("frontend-scope-audit failed:");
  console.error(error);
  process.exit(1);
});


