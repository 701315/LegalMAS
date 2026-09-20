const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');

if (fs.existsSync(pagePath)) {
  let content = fs.readFileSync(pagePath, 'utf-8');

  // Старая обертка с иконкой Network
  const oldPlaceholderRegex = /<motion\.div[\s\S]*?className="hidden lg:block relative overflow-hidden bg-\[var\(--bg-surface\)\][\s\S]*?<\/motion\.div>/;

  // Новый блок с реальным изображением /counterpaties picture.png
  const newImageBlock = `<motion.div
            initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="relative overflow-hidden border border-[var(--border-color)]/40 bg-[var(--bg-surface)] shadow-sm"
          >
            <img
              src="/counterpaties picture.png"
              alt="Counterparty and Related Party Verification"
              className="block w-full h-auto object-cover"
            />
          </motion.div>`;

  content = content.replace(oldPlaceholderRegex, newImageBlock);

  fs.writeFileSync(pagePath, content, 'utf-8');
  console.log('✅ CounterpartiesPage.tsx: Изображение /counterpaties picture.png успешно установлено в Hero-сегмент!');
}
