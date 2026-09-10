import React from 'react';
import Reveal from '../../motion/Reveal';
import { useTranslation } from 'react-i18next';

interface Principle {
  title: string;
  desc: string;
}

const AboutPrinciplesSection: React.FC = () => {
  const { t } = useTranslation('marketing');

  // Безопасное получение массива принципов из i18n
  const principlesRaw = t('about.principles.items', { returnObjects: true });
  const principles = Array.isArray(principlesRaw) 
    ? (principlesRaw as Principle[]) 
    : [];

  return (
    <section className="bg-[var(--bg-base)] py-24 border-t border-[var(--border-color)]">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
        <Reveal>
          <h2 className="text-h1 text-[var(--text-primary)] text-start mb-12">
            {t('about.principles.title')}
          </h2>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {principles.map((p, i) => (
            <Reveal key={i}>
              {/* RTL FIX: border-l-2 → border-s-2, pl-6 → ps-6 */}
              <div className="border-s-2 border-[var(--border-color)] ps-6">
                <h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">
                  {p.title}
                </h3>
                <p className="text-body leading-relaxed text-[var(--text-secondary)] text-start mt-3">
                  {p.desc}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
};

export default AboutPrinciplesSection;
