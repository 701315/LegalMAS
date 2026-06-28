// scripts/generate-roots.mjs
// Генератор корневой системы с заострением, длинным главным корнем
// и более распределёнными боковыми корнями.

import { writeFileSync } from "fs";

const WIDTH = 1400;
// Увеличил HEIGHT, чтобы главный корень мог уйти ниже
const HEIGHT = 1300;

const ORIGIN_X = WIDTH / 2;
const ORIGIN_Y = 40;

// ─── Seeded random ────────────────────────────────────
function makeRng(seed) {
  let s = seed >>> 0;
  return function () {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

const SEED = parseInt(process.argv[2]) || 42;
const rand = makeRng(SEED);

function randRange(min, max) {
  return min + rand() * (max - min);
}

function randInt(min, max) {
  return Math.floor(randRange(min, max + 1));
}

// ─── Генерация корня с заострением ───────────────────
function generateRoot(opts) {
  const {
    startX,
    startY,
    angle,
    length,
    thickness,
    endThickness = 1.5,
    depth = 0,
    maxDepth = 3,
    branchProbability = 1.0,  // насколько часто будут ветвления
  } = opts;

  const allSegments = [];
  const numPoints = randInt(18, 28);
  const points = [{ x: startX, y: startY }];

  let currentX = startX;
  let currentY = startY;
  let currentAngle = angle;

  for (let i = 0; i < numPoints; i++) {
    currentAngle += randRange(-0.2, 0.2);

    const gravityPull = 0.06 * (1 - depth * 0.2);
    if (currentAngle < Math.PI / 2) {
      currentAngle += gravityPull;
    } else if (currentAngle > Math.PI / 2) {
      currentAngle -= gravityPull * 0.5;
    }

    const stepLen = (length / numPoints) * randRange(0.7, 1.3);
    currentX += Math.cos(currentAngle) * stepLen;
    currentY += Math.sin(currentAngle) * stepLen;

    currentY = Math.min(currentY, HEIGHT - 10);
    currentX = Math.max(20, Math.min(currentX, WIDTH - 20));

    points.push({ x: currentX, y: currentY });
  }

  // Рисуем как множество отрезков с убывающей толщиной
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];
    const t = i / (points.length - 1);
    const taper = 1 - Math.pow(t, 1.3);
    const segThickness = endThickness + (thickness - endThickness) * taper;

    allSegments.push({
      x1: p1.x,
      y1: p1.y,
      x2: p2.x,
      y2: p2.y,
      thickness: segThickness,
      depth,
    });
  }

  // Ветвления
  if (depth < maxDepth && thickness > 5) {
    const baseBranches = depth === 0 ? randInt(2, 4) : randInt(1, 3);
    const numBranches = Math.round(baseBranches * branchProbability);

    for (let b = 0; b < numBranches; b++) {
      const t = randRange(0.3, 0.85);
      const branchIndex = Math.floor(t * (points.length - 1));
      const branchPoint = points[branchIndex];
      if (!branchPoint) continue;

      const angleVariance = 1.1 - depth * 0.25;
      const branchAngle = currentAngle + randRange(-angleVariance, angleVariance);
      const branchLength = length * randRange(0.3, 0.55);

      const parentTaper = 1 - Math.pow(t, 1.3);
      const parentThicknessHere = endThickness + (thickness - endThickness) * parentTaper;
      const branchThickness = parentThicknessHere * randRange(0.5, 0.75);

      if (branchLength > 30 && branchThickness > 1.8) {
        const subSegments = generateRoot({
          startX: branchPoint.x,
          startY: branchPoint.y,
          angle: branchAngle,
          length: branchLength,
          thickness: branchThickness,
          endThickness: 1.2,
          depth: depth + 1,
          maxDepth,
          branchProbability: branchProbability * 0.8,
        });
        allSegments.push(...subSegments);
      }
    }
  }

  return allSegments;
}

// ─── Главная генерация ───────────────────────────────
console.log(`🌱 Generating roots with seed=${SEED}...`);

const allSegments = [];

// 1. Воротник
const collarWidth = 240;
const collarHeight = 55;
allSegments.push({
  type: "ellipse",
  cx: ORIGIN_X,
  cy: ORIGIN_Y,
  rx: collarWidth / 2,
  ry: collarHeight / 2,
});

// 2. Переходная трапеция
const transitionPoints = [
  { x: ORIGIN_X - 120, y: ORIGIN_Y + 10 },
  { x: ORIGIN_X + 120, y: ORIGIN_Y + 10 },
  { x: ORIGIN_X + 75, y: ORIGIN_Y + 70 },
  { x: ORIGIN_X - 75, y: ORIGIN_Y + 70 },
];
allSegments.push({
  type: "polygon",
  points: transitionPoints,
});

// 3. ГЛАВНЫЙ СТЕРЖНЕВОЙ корень — идёт до самого низа canvas
allSegments.push(
  ...generateRoot({
    startX: ORIGIN_X + randRange(-15, 15),
    startY: ORIGIN_Y + 55,
    angle: Math.PI / 2 + randRange(-0.08, 0.08),
    length: HEIGHT * 0.95,        // было 0.85 → стало 0.95
    thickness: 60,                 // было 55 → 60 (толще)
    endThickness: 1.5,
    depth: 0,
    maxDepth: 3,
    branchProbability: 1.0,
  })
);

// 4. БОКОВЫЕ корни — меньше штук, лучше распределённые
const numSideRoots = randInt(5, 7);  // было 7-10 → стало 5-7
console.log(`  Side main roots: ${numSideRoots}`);

// Распределяем углы равномерно с большим разбросом
const angleSpread = [];
for (let i = 0; i < numSideRoots; i++) {
  const t = i / Math.max(1, numSideRoots - 1);
  // От 0.08π до 0.92π — почти горизонтально с обеих сторон
  const baseAngle = Math.PI * (0.08 + 0.84 * t);
  const angle = baseAngle + randRange(-0.2, 0.2);
  angleSpread.push(angle);
}

// КЛЮЧЕВОЕ: распределяем стартовые точки по всей ширине воротника
// (не из центра, а из разных мест) — это даёт расхождение
const collarHalf = collarWidth / 2;

for (let i = 0; i < numSideRoots; i++) {
  const angle = angleSpread[i];

  // Стартовая X-координата привязана к углу:
  // корни идущие влево (angle < π/2) стартуют ближе к левому краю воротника,
  // корни идущие вправо стартуют ближе к правому
  const angleNormalized = (angle - Math.PI * 0.08) / (Math.PI * 0.84); // 0..1
  const startX = ORIGIN_X + (angleNormalized - 0.5) * collarWidth * 0.85
                          + randRange(-15, 15);

  const startY = ORIGIN_Y + randRange(25, 60);

  const length = HEIGHT * randRange(0.55, 0.85);
  const thickness = randRange(22, 38);

  allSegments.push(
    ...generateRoot({
      startX,
      startY,
      angle,
      length,
      thickness,
      endThickness: 1.5,
      depth: 0,
      maxDepth: 3,
      branchProbability: 0.9,
    })
  );
}

console.log(`  Total segments: ${allSegments.length}`);

// ─── Собираем SVG ────────────────────────────────────
const svgElements = allSegments
  .map((s) => {
    if (s.type === "ellipse") {
      return `<ellipse cx="${s.cx}" cy="${s.cy}" rx="${s.rx}" ry="${s.ry}" />`;
    }
    if (s.type === "polygon") {
      const pts = s.points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
      return `<polygon points="${pts}" />`;
    }
    return `<line x1="${s.x1.toFixed(1)}" y1="${s.y1.toFixed(1)}" x2="${s.x2.toFixed(1)}" y2="${s.y2.toFixed(1)}" stroke="#000" stroke-width="${s.thickness.toFixed(1)}" stroke-linecap="round" fill="none" />`;
  })
  .filter(Boolean)
  .join("\n  ");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${WIDTH} ${HEIGHT}" width="${WIDTH}" height="${HEIGHT}">
  <g fill="#000000">
  ${svgElements}
  </g>
</svg>`;

writeFileSync("public/roots-mask.svg", svg, "utf8");

console.log(`✅ Generated public/roots-mask.svg`);
console.log(`   Size: ${(svg.length / 1024).toFixed(1)} KB`);
console.log(`   Seed: ${SEED}`);