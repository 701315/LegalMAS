const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  const updatedCapabilities = `function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.corporateLegal.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="max-w-2xl mb-16">
          <p className="text-eyebrow mb-4 text-start">
            {t("solutions.corporateLegal.capabilities.eyebrow")}
          </p>
          <h2 className="text-h1 text-[var(--text-primary)] mb-16 max-w-none text-start">
            {t("solutions.corporateLegal.capabilities.title")}
          </h2>
        </div>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Layers;
            const bulletsRaw = t(\`solutions.corporateLegal.capabilities.items.\${index}.bullets\`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <div key={item.id || index} className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
                <div className="md:col-span-4">
                  <div className="flex items-center gap-3">
                    <IconComponent className="h-5 w-5 text-[var(--accent-primary)] opacity-50 flex-shrink-0" />
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                      {item.title}
                    </h2>
                  </div>
                </div>
                <div className="md:col-span-8">
                  <ul className="space-y-4">
                    {bullets.map((bullet, bIndex) => (
                      <li key={\`\${item.id}-bullet-\${bIndex}\`} className="flex items-start gap-3 text-start">
                        <CheckCircle2 className="h-4 w-4 text-[var(--accent-primary)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-body-sm">
                          {bullet}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}`;

  content = content.replace(/function CapabilitiesSection\(\) \{[\s\S]*?\n\}/, updatedCapabilities);

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: CapabilitiesSection (Array structuring, Playbook application...) полностью выровнена по стандарту Compliance!');
}
