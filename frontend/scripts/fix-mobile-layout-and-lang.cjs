const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');
const mobileMenuPath = path.join(__dirname, '../src/marketing/components/shared/MobileMenu.tsx');

console.log('\n===============================================================');
console.log('🛠️ ИСПРАВЛЕНИЕ МОБИЛЬНОЙ ВЕРСТКИ И СЕЛЕКТОРА ЯЗЫКОВ');
console.log('===============================================================\n');

// 1. Обновляем SiteHeader.tsx - кнопка выбора языка показывается ТОЛЬКО на десктопе (hidden lg:flex)
if (fs.existsSync(headerPath)) {
  let content = fs.readFileSync(headerPath, 'utf-8');

  // Оборачиваем десктопный языковой dropdown в hidden lg:block
  content = content.replace(
    /<div className="relative" ref=\{langDropdownRef\}>/g,
    '<div className="relative hidden lg:block" ref={langDropdownRef}>'
  );

  fs.writeFileSync(headerPath, content, 'utf-8');
  console.log('✅ SiteHeader.tsx: Языковой селектор на мобильных вынесен из шапки, хедер не ломается!');
}

// 2. Обновляем MobileMenu.tsx - делаем выбор языка удобным рядом с крупными кнопками
if (fs.existsSync(mobileMenuPath)) {
  let content = fs.readFileSync(mobileMenuPath, 'utf-8');

  const cleanLangSection = `
            {/* МОБИЛЬНЫЙ ПЕРЕКЛЮЧАТЕЛЬ ЯЗЫКОВ */}
            <div className="pt-6 border-t border-[var(--border-color)]">
              <p className="text-meta font-bold uppercase text-[var(--text-muted)] mb-3 text-start">
                Language / Язык
              </p>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { code: "en", label: "EN" },
                  { code: "ru", label: "RU" },
                  { code: "ar", label: "AR" },
                  { code: "tr", label: "TR" }
                ].map((lang) => {
                  const isActive = i18n.language === lang.code;
                  return (
                    <button
                      key={lang.code}
                      onClick={() => handleLanguageChange(lang.code)}
                      className={\`py-2.5 px-3 rounded-lg text-body-sm font-bold transition-all text-center border \${
                        isActive
                          ? "bg-[var(--accent-primary)] text-white border-[var(--accent-primary)] shadow-sm"
                          : "bg-[var(--bg-surface)] text-[var(--text-primary)] border-[var(--border-color)] hover:border-[#1A1917]"
                      }\`}
                    >
                      {lang.label}
                    </button>
                  );
                })}
              </div>
            </div>`;

  // Заменяем старую аккордеонную логику мобильного языка на чистую сетку 4 кнопок
  content = content.replace(
    /<div className="border-t border-\[var\(--border-color\)\] pt-4">[\s\S]*?<\/ul>\s*<\/div>\s*<\/div>/g,
    cleanLangSection
  );

  fs.writeFileSync(mobileMenuPath, content, 'utf-8');
  console.log('✅ MobileMenu.tsx: Выбор языка заменён на удобную сетку из 4 кнопок (EN, RU, AR, TR)!');
}

console.log('\n===============================================================\n');
