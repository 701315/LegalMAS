const fs = require('fs');
const path = require('path');

const iaPath = path.join(__dirname, '../src/marketing/pages/solutions/InternalAuditPage.tsx');

if (fs.existsSync(iaPath)) {
  let content = fs.readFileSync(iaPath, 'utf-8');

  const cleanCap = `function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.internalAuditPage.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl mb-16">
            <p className="text-eyebrow mb-4 text-start">
              {t("solutions.internalAuditPage.capabilities.eyebrow")}
            </p>
            <h2 className="text-h1 whitespace-pre-line text-start">
              {t("solutions.internalAuditPage.capabilities.titlePart1")}
              <br />
              <span className="italic font-normal text-[var(--accent-primary)]">
                {t("solutions.internalAuditPage.capabilities.titlePart2")}
              </span>
            </h2>
          </div>
        </Reveal>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Layers;
            const bulletsRaw = t(\`solutions.internalAuditPage.capabilities.items.\${index}.bullets\`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <Reveal key={item.id} delay={index * 0.05}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
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
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}`;

  content = content.replace(/function CapabilitiesSection\(\) \{[\s\S]*?\n\}/, cleanCap);

  fs.writeFileSync(iaPath, content, 'utf-8');
  console.log('✅ InternalAuditPage.tsx: CapabilitiesSection полностью выровнена по образцу CompliancePage (h2, font-serif, italic, py-10)!');
}
