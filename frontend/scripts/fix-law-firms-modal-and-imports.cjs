const fs = require('fs');
const path = require('path');

const lawPath = path.join(__dirname, '../src/marketing/pages/solutions/LawFirmsPage.tsx');

if (fs.existsSync(lawPath)) {
  let content = fs.readFileSync(lawPath, 'utf-8');

  // 1. Убираем ExternalLink из импорта
  content = content.replace(/ExternalLink,?\n?/g, '');

  // 2. Меняем ContactModal на useContactModal из контекста
  content = content.replace(
    /import ContactModal from "\.\.\/\.\.\/components\/home\/ContactModal";/g,
    'import { useContactModal } from "../../context/ContactModalContext";'
  );

  // 3. Обновляем компонент LawFirmsPage
  const updatedComponent = `const LawFirmsPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <HowSteloomHelpsSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};`;

  content = content.replace(/const LawFirmsPage: React\.FC = \(\) => \{[\s\S]*?\n\};/, updatedComponent);

  fs.writeFileSync(lawPath, content, 'utf-8');
  console.log('✅ LawFirmsPage.tsx: ExternalLink и модальное окно исправлены!');
}
