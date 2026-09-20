const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  // 1. Меняем импорт ContactModal на useContactModal из контекста
  content = content.replace(
    /import ContactModal from "\.\.\/\.\.\/components\/home\/ContactModal";/g,
    'import { useContactModal } from "../../context/ContactModalContext";'
  );

  // 2. Обновляем главный компонент CorporateLegalPage
  const updatedComponent = `const CorporateLegalPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection />
        <PressureSection />
        <OutcomesSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};`;

  content = content.replace(/const CorporateLegalPage: React\.FC = \(\) => \{[\s\S]*?\n\};/, updatedComponent);

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: Контекст модального окна успешно обновлен!');
}
