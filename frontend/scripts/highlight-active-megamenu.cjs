const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');

if (fs.existsSync(headerPath)) {
  let content = fs.readFileSync(headerPath, 'utf-8');

  // Убедимся, что const location = useLocation(); объявлен внутри компонента
  if (!content.includes('const location = useLocation();')) {
    content = content.replace(
      /const \{ t, i18n \} = useTranslation\("marketing"\);/g,
      'const { t, i18n } = useTranslation("marketing");\n  const location = useLocation();'
    );
  }

  // Обновляем рендеринг пунктов мегаменю
  const oldItemRender = /<li key=\{i\.href\}>[\s\S]*?<Link[\s\S]*?className="group block"[\s\S]*?<p className="text-body-sm !font-bold !text-\[#1A1917\] group-hover:!text-\[var\(--accent-primary\)\] transition-colors">\s*\{i\.label\}\s*<\/p>[\s\S]*?<p className="text-body-sm text-gray-500 font-normal leading-relaxed mt-1">\s*\{i\.description\}\s*<\/p>[\s\S]*?<\/Link>\s*<\/li>/g;

  const newItemRender = `<li key={i.href}>
                            {(() => {
                              const isActive = location.pathname === i.href;
                              return (
                                <Link
                                  to={i.href}
                                  onClick={() => setSolutionsOpen(false)}
                                  className={\`group block p-2 rounded-lg transition-colors \${isActive ? 'bg-[var(--accent-primary)]/10' : 'hover:bg-black/5'}\`}
                                >
                                  <p className={\`text-body-sm !font-bold transition-colors \${isActive ? '!text-[var(--accent-primary)]' : '!text-[#1A1917] group-hover:!text-[var(--accent-primary)]'}\`}>
                                    {i.label}
                                  </p>
                                  <p className={\`text-body-sm font-normal leading-relaxed mt-0.5 transition-colors \${isActive ? 'text-[var(--text-primary)]' : 'text-gray-500'}\`}>
                                    {i.description}
                                  </p>
                                </Link>
                              );
                            })()}
                          </li>`;

  // Резервная замена через замену JSX шаблона
  const original = content;
  content = content.replace(
    /<Link\s+to=\{i\.href\}[\s\S]*?onClick=\{\(\) => setSolutionsOpen\(false\)\}[\s\S]*?className="group block"[\s\S]*?<\/Link>/g,
    `{(() => {
                              const isActive = location.pathname === i.href;
                              return (
                                <Link
                                  to={i.href}
                                  onClick={() => setSolutionsOpen(false)}
                                  className={\`group block p-2 -mx-2 rounded-md transition-all duration-200 \${isActive ? 'bg-[var(--accent-primary)]/10' : 'hover:bg-black/[0.03]'}\`}
                                >
                                  <p className={\`text-body-sm !font-bold transition-colors \${isActive ? '!text-[var(--accent-primary)]' : '!text-[#1A1917] group-hover:!text-[var(--accent-primary)]'}\`}>
                                    {i.label}
                                  </p>
                                  <p className={\`text-body-sm font-normal leading-relaxed mt-0.5 transition-colors \${isActive ? 'text-[var(--text-primary)] font-medium' : 'text-gray-500'}\`}>
                                    {i.description}
                                  </p>
                                </Link>
                              );
                            })()}`
  );

  fs.writeFileSync(headerPath, content, 'utf-8');
  console.log('✅ SiteHeader.tsx: Активный пункт выпадающего меню теперь подсвечивается фиремнным рыжим акцентом!');
}
