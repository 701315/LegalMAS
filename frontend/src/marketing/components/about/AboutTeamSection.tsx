import React from 'react';
import { useTranslation } from 'react-i18next';
import Reveal from '../../motion/Reveal';

const AboutTeamSection: React.FC = () => {
  // Оставляем только t, так как i18n не используется напрямую
  const { t } = useTranslation('marketing');
  
  // Защита от сбоев при получении массива из i18n
  const blocksRaw = t('about.team.blocks', { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32 border-t border-[var(--border-color)]">
      <div 
        className="mx-auto w-full px-6 lg:px-8" 
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-12 lg:gap-24">
          
          {/* ── Левая колонка: Заголовок и вводный текст ────────────────── */}
          <div className="lg:col-span-4 lg:sticky lg:top-32 h-fit">
            <Reveal>
              <h2 className="text-h1 text-[var(--text-primary)] text-start">
                {t('about.team.title')}
              </h2>
              <p className="mt-6 text-body leading-normal text-[var(--text-secondary)] max-w-sm text-start">
                {t('about.team.intro')}
              </p>
            </Reveal>
          </div>

          {/* ── Правая колонка: Сетка 2x2 ──────────────────────────────── */}
          <div className="lg:col-span-8">
            <div className="grid grid-cols-1 gap-12 md:grid-cols-2 lg:gap-16">
              {blocks.map((block, i) => (
                <Reveal key={block.id || i} delay={i * 0.1}>
                  <div className="flex flex-col items-start text-start">
                    <div className="w-full max-w-[380px] aspect-[3/2] overflow-hidden rounded-[2rem] bg-[var(--bg-surface)] border border-[var(--border-color)]">
                      <img 
                        src={block.image} 
                        alt={block.title}
                        className="h-full w-full object-cover grayscale-[0.2] hover:grayscale-0 transition-all duration-700"
                      />
                    </div>
                    
                    <h3 className="mt-8 text-h2 font-serif text-[var(--text-primary)] text-start">
                      {block.title}
                    </h3>
                    
                    <p className="mt-4 text-body-sm leading-normal text-[var(--text-secondary)] max-w-[380px]">
                      {block.description}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default AboutTeamSection;