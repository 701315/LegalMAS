// src/marketing/components/security/SecurityCTASection.tsx
import React from 'react';
import { ArrowRight } from 'lucide-react';
import Reveal from '../../motion/Reveal';
import { useContactModal } from '../../context/ContactModalContext';
import { useTranslation } from 'react-i18next';

/**
 * SecurityCTASection — финальная CTA-секция страницы Security.
 * Композиция идентична PlatformCTASection, с поддержкой i18n и RTL.
 */
const SecurityCTASection: React.FC = () => {
  const { openContactModal } = useContactModal();
  const { t, i18n } = useTranslation('security');
  const isRTL = i18n.language === 'ar';

  // Безопасное получение массива абзацев
  const paragraphsRaw = t('cta.paragraphs', { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) 
    ? paragraphsRaw 
    : [t('cta.paragraphs')];

  return (
    <section
      className="relative"
      style={{ background: '#FAF8F5' }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            {/* Верхний тонкий якорь */}
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            {/* ✅ Заголовок — используем whitespace-pre-line вместо ручного .split('\n') */}
            <h2 className="mt-10 text-h1 whitespace-pre-line">
              {t('cta.title')}
            </h2>

            {/* Абзацы */}
            <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
              {paragraphs.map((p: string, i: number) => (
                <p
                  key={i}
                  className="text-body leading-[1.75] text-[var(--text-secondary)]"
                >
                  {p}
                </p>
              ))}
            </div>

            {/* Одна CTA-кнопка */}
            <div className="mt-10 flex items-center justify-center">
              <button
                type="button"
                onClick={openContactModal}
                className="cta-primary inline-flex items-center gap-2"
              >
                {t('cta.ctaPrimary')}
                {/* RTL FIX: разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ 
                    transform: isRTL ? 'rotate(180deg)' : 'none',
                    transition: 'transform 0.2s ease'
                  }} 
                />
              </button>
            </div>

            {/* Мета-строка */}
            <p className="mt-8 text-eyebrow leading-[1.6] text-[var(--text-muted)]">
              {t('cta.meta')}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default SecurityCTASection;