#!/usr/bin/env node

/**
 * DEV STATIC FRONTEND ENTERPRISE AUDIT
 * -------------------------------------
 * Проверяет архитектуру адаптивности и UX best-practice
 * Только статический анализ кода (без Playwright).
 */

import fs from "fs";
import path from "path";

/* ============================================================
   CONFIG
============================================================ */

const ROOT = "/srv/steloom-dev/frontend/src";
const IGNORE_DIRS = new Set(["node_modules", "dist", "build", "marketing"]);
const EXT = new Set([".tsx", ".ts", ".jsx", ".js"]);

const RESPONSIVE_PREFIXES = ["sm:", "md:", "lg:", "xl:", "2xl:"];

const findings = [];

/* ============================================================
   FILE WALKER
============================================================ */

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (IGNORE_DIRS.has(entry.name)) continue;

    const full = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      walk(full, files);
    } else if (EXT.has(path.extname(entry.name))) {
      files.push(full);
    }
  }
  return files;
}

/* ============================================================
   RULE HELPERS
============================================================ */

function add(rule, severity, file, line, message) {
  findings.push({ rule, severity, file, line, message });
}

/* ============================================================
   RULES
============================================================ */

function checkFile(file) {
  const content = fs.readFileSync(file, "utf8");
  const lines = content.split(/\r?\n/);

  /* 1️⃣ grid-cols без mobile-first */
  lines.forEach((line, i) => {
    const match = line.match(/grid-cols-(\d+)/);
    if (match) {
      const cols = parseInt(match[1]);
      const hasMobileFirst = line.includes("grid-cols-1");
      const hasResponsive = RESPONSIVE_PREFIXES.some(p =>
        line.includes(p + "grid-cols-")
      );

      if (cols >= 3 && !hasMobileFirst && !hasResponsive) {
        add(
          "GRID_NOT_MOBILE_FIRST",
          "error",
          file,
          i + 1,
          `grid-cols-${cols} без mobile-first или breakpoint`
        );
      }
    }
  });

  /* 2️⃣ flex-row без wrap или breakpoint */
  lines.forEach((line, i) => {
    if (
      line.includes("flex-row") &&
      !line.includes("flex-wrap") &&
      !RESPONSIVE_PREFIXES.some(p => line.includes(p))
    ) {
      add(
        "FLEX_ROW_NO_WRAP",
        "warn",
        file,
        i + 1,
        "flex-row без wrap или breakpoint"
      );
    }
  });

  /* 3️⃣ inline px */
  lines.forEach((line, i) => {
    if (line.includes("style={{") && line.match(/\d+px/)) {
      add(
        "INLINE_PX",
        "warn",
        file,
        i + 1,
        "Inline px размер — проверить адаптивность"
      );
    }
  });

  /* 4️⃣ absolute/fixed + высокий z-index */
  lines.forEach((line, i) => {
    if (
      (line.includes("absolute") || line.includes("fixed")) &&
      line.match(/z-\[\d+/)
    ) {
      add(
        "HIGH_ZINDEX_POSITIONED",
        "warn",
        file,
        i + 1,
        "absolute/fixed с высоким z-index — риск перекрытия"
      );
    }
  });

  /* 5️⃣ отсутствие responsive prefix в layout */
  if (
    file.includes("pages") ||
    file.includes("layout")
  ) {
    const hasResponsive = RESPONSIVE_PREFIXES.some(p =>
      content.includes(p)
    );

    if (!hasResponsive) {
      add(
        "NO_RESPONSIVE_CLASSES",
        "info",
        file,
        1,
        "В файле нет sm:/md:/lg: классов"
      );
    }
  }

  /* 6️⃣ img без alt */
  lines.forEach((line, i) => {
    if (line.includes("<img") && !line.includes("alt=")) {
      add(
        "IMG_NO_ALT",
        "error",
        file,
        i + 1,
        "img без alt"
      );
    }
  });

  /* 7️⃣ div с onClick без role */
  lines.forEach((line, i) => {
    if (
      line.includes("onClick") &&
      line.includes("<div") &&
      !line.includes("role=")
    ) {
      add(
        "DIV_CLICK_NO_ROLE",
        "warn",
        file,
        i + 1,
        "div с onClick без role"
      );
    }
  });

  /* 8️⃣ window.innerWidth без matchMedia */
  if (content.includes("window.innerWidth") &&
      !content.includes("matchMedia")) {
    add(
      "INNERWIDTH_NO_MATCHMEDIA",
      "warn",
      file,
      1,
      "window.innerWidth без matchMedia — риск неадаптивности"
    );
  }

  /* 9️⃣ overflow-hidden на root */
  lines.forEach((line, i) => {
    if (
      line.includes("overflow-hidden") &&
      line.includes("className")
    ) {
      add(
        "OVERFLOW_HIDDEN_RISK",
        "warn",
        file,
        i + 1,
        "overflow-hidden — риск ломки mobile scroll"
      );
    }
  });

  /* 🔟 кнопка без type */
  lines.forEach((line, i) => {
    if (
      line.includes("<button") &&
      !line.includes("type=")
    ) {
      add(
        "BUTTON_NO_TYPE",
        "info",
        file,
        i + 1,
        "button без type — лучше явно указать"
      );
    }
  });
}

/* ============================================================
   RUN
============================================================ */

function run() {
  const files = walk(ROOT);

  files.forEach(checkFile);

  const errors = findings.filter(f => f.severity === "error");
  const warns = findings.filter(f => f.severity === "warn");
  const infos = findings.filter(f => f.severity === "info");

  console.log("\n========== STATIC FRONTEND AUDIT ==========\n");
  console.log(`Errors: ${errors.length}`);
  console.log(`Warnings: ${warns.length}`);
  console.log(`Info: ${infos.length}\n`);

  findings.forEach(f => {
    console.log(
      `[${f.severity.toUpperCase()}] ${f.file}:${f.line} → ${f.rule} → ${f.message}`
    );
  });

  fs.writeFileSync(
    "dev-static-frontend-audit-report.json",
    JSON.stringify({ findings }, null, 2)
  );

  if (errors.length > 0) process.exitCode = 1;
}

run();


