// scripts/prerender.mjs
// Запускается после vite build.
// Обходит публичные маршруты через headless Chromium,
// сохраняет готовый HTML в dist/.

import puppeteer from "puppeteer";
import { createServer } from "node:http";
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import handler from "serve-handler";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST_DIR  = join(__dirname, "..", "dist");
const PORT      = 3033;

// Только публичные маркетинговые маршруты из App.tsx.
// Не включаем /login, /dashboard, /admin/* — они за RequireAuth.
const ROUTES = [
  "/",
  "/capabilities",
  "/security",
  "/about",
  "/demo",
  "/solutions/ma-due-diligence",
  "/solutions/contract-review",
  "/solutions/compliance",
  "/solutions/internal-audit",
  "/solutions/law-firms",
  "/solutions/corporate-legal",
  "/solutions/audit-compliance",
  "/solutions/counterparties",
  "/solutions/real-estate",
];

// ── Локальный статический сервер ──────────────────────────────
function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      handler(req, res, {
        public: DIST_DIR,
        // SPA-fallback: любой неизвестный путь → index.html
        rewrites: [{ source: "**", destination: "/index.html" }],
      });
    });
    server.listen(PORT, () => {
      console.log(`  Server: http://localhost:${PORT}`);
      resolve(server);
    });
  });
}

// ── Сохранение HTML ───────────────────────────────────────────
function saveHtml(route, html) {
  let outPath;
  if (route === "/") {
    outPath = join(DIST_DIR, "index.html");
  } else {
    const dir = join(DIST_DIR, route);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    outPath = join(dir, "index.html");
  }
  writeFileSync(outPath, html, "utf8");
  return outPath.replace(join(__dirname, "..") + "/", "");
}

// ── Основной процесс ──────────────────────────────────────────
async function prerender() {
  console.log("\n🔄 Prerender started\n");

  if (!existsSync(DIST_DIR)) {
    console.error("❌ dist/ not found. Run `vite build` first.");
    process.exit(1);
  }

  const server = await startServer();

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const failed = [];

  for (const route of ROUTES) {
    const url = `http://localhost:${PORT}${route}`;
    process.stdout.write(`  ${route.padEnd(40)}`);

    try {
      const page = await browser.newPage();

      // Блокируем fetch/xhr — API-запросы к бэкенду не нужны при prerender
      await page.setRequestInterception(true);
      page.on("request", (req) => {
        const t = req.resourceType();
        if (t === "fetch" || t === "xhr") {
          req.abort();
        } else {
          req.continue();
        }
      });

      // Подавляем console.error чтобы не засорять вывод
      page.on("console", (msg) => {
        if (msg.type() === "error") return;
      });

      await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });

      // Ждём пока #root наполнится реальным контентом
      await page.waitForFunction(
        () => {
          const root = document.getElementById("root");
          return root && root.children.length > 0;
        },
        { timeout: 15000 }
      );

      // Пауза для framer-motion и CSS transitions
      await new Promise((r) => setTimeout(r, 600));

      const html    = await page.content();
      const relPath = saveHtml(route, html);
      await page.close();

      console.log(`✅  ${relPath}`);
    } catch (err) {
      console.log(`❌  FAILED`);
      console.error(`     ${err.message}`);
      failed.push({ route, error: err.message });
    }
  }

  await browser.close();
  server.close();

  const ok = ROUTES.length - failed.length;
  console.log(`\n✅ Done: ${ok}/${ROUTES.length} routes prerendered\n`);

  if (failed.length > 0) {
    console.log("⚠️  Failed:");
    failed.forEach((r) => console.log(`   ${r.route}: ${r.error}`));
    process.exit(1);
  }
}

prerender().catch((err) => {
  console.error("❌ Prerender crashed:", err);
  process.exit(1);
});
