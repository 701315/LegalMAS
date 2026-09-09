// scripts/prerender.mjs
import puppeteer from "puppeteer";
import { createServer } from "node:http";
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import handler from "serve-handler";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST_DIR  = join(__dirname, "..", "dist");
const PORT      = 3033;

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

function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      handler(req, res, {
        public: DIST_DIR,
        rewrites: [{ source: "**", destination: "/index.html" }],
      });
    });
    server.listen(PORT, () => {
      console.log(`  Server: http://localhost:${PORT}`);
      resolve(server);
    });
  });
}

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

async function prerender() {
  console.log("\n🔄 Prerender started\n");

  if (!existsSync(DIST_DIR)) {
    console.error("❌ dist/ not found. Run `vite build` first.");
    process.exit(1);
  }

  const server = await startServer();

  const browser = await puppeteer.launch({
    headless: "new", // Более стабильный режим headless в новых версиях
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const failed = [];

  for (const route of ROUTES) {
    const url = `http://localhost:${PORT}${route}`;
    process.stdout.write(`  ${route.padEnd(40)}`);

    try {
      const page = await browser.newPage();

      // УЛУЧШЕННАЯ интерцепция запросов
      await page.setRequestInterception(true);
      page.on("request", (req) => {
        const reqUrl = req.url();
        const t = req.resourceType();
        
        // ✅ РАЗРЕШАЕМ загрузку JSON (критично для i18next!) и статических ассетов
        if (reqUrl.includes('.json') || reqUrl.includes('locales')) {
          req.continue();
        } 
        // Блокируем только явные API-запросы к бэкенду, если они есть
        else if (t === "fetch" || t === "xhr") {
          if (reqUrl.includes('/api/')) {
            req.abort();
          } else {
            req.continue();
          }
        } else {
          req.continue();
        }
      });

      // Ловим реальные ошибки React/JS, чтобы понимать причину падений
      let jsErrors = [];
      page.on("pageerror", (err) => {
        jsErrors.push(err.message);
      });
      
      page.on("console", (msg) => {
        if (msg.type() === "error") {
          jsErrors.push(msg.text());
        }
      });

      // Увеличиваем таймаут для тяжёлой главной страницы
      await page.goto(url, { waitUntil: "networkidle0", timeout: 45000 });

      // Более надёжная проверка: ждём появления тега <main> или <h1>, а не просто детей root
      await page.waitForFunction(
        () => {
          return document.querySelector("main") !== null || document.querySelector("h1") !== null;
        },
        { timeout: 20000 }
      );

      // Пауза для завершения framer-motion анимаций
      await new Promise((r) => setTimeout(r, 800));

      const html = await page.content();
      
      if (jsErrors.length > 0) {
        console.log(`⚠️  WARN (rendered with JS errors)`);
        console.error(`     ${jsErrors.join(" | ")}`);
      }

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
    console.log("⚠️  Failed routes:");
    failed.forEach((r) => console.log(`   • ${r.route}: ${r.error}`));
    // process.exit(1); // Можно раскомментировать, если хотите падение CI/CD при ошибках
  }
}

prerender().catch((err) => {
  console.error("❌ Prerender crashed:", err);
  process.exit(1);
});

