// src/marketing/components/about/AboutPhilosophySection.tsx
import React from 'react';
import Reveal from '../../motion/Reveal';
import { useTranslation } from 'react-i18next';

const AboutPhilosophySection: React.FC = () => {
  const { t } = useTranslation('marketing');

  // Безопасное получение массивов из i18n
  const card1TagsRaw = t('about.philosophy.card1.tags', { returnObjects: true });
  const card1Tags = Array.isArray(card1TagsRaw) ? card1TagsRaw : [];

  const card2BadgesRaw = t('about.philosophy.card2.badges', { returnObjects: true });
  const card2Badges = Array.isArray(card2BadgesRaw) ? card2BadgesRaw : [];

  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
        <div className="grid md:grid-cols-2 gap-8 lg:gap-12">
          
          {/* Card 1: Infrastructure */}
          <Reveal>
            <div className="card-surface p-10 lg:p-12 flex flex-col h-full justify-between border-[var(--border-color)]">
              <div>
                <p className="eyebrow">{t('about.philosophy.card1.eyebrow')}</p>
                <h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">
                  {t('about.philosophy.card1.title')}
                </h3>
                <p className="mt-6 text-body leading-relaxed text-[var(--text-secondary)] text-start">
                  {t('about.philosophy.card1.description')}
                </p>
              </div>
              <ul className="mt-10 space-y-3">
                {card1Tags.map((tag: string) => (
                  <li key={tag} className="flex items-center gap-3 text-meta font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    <span className="h-1 w-1 rounded-full bg-[var(--color-accent)]" /> {tag}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          {/* Card 2: Output */}
          <Reveal>
            <div className="rounded-2xl border border-[var(--border-color)] bg-[var(--bg-surface)] p-10 lg:p-12 flex flex-col h-full justify-between">
              <div>
                <p className="eyebrow">{t('about.philosophy.card2.eyebrow')}</p>
                <h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">
                  {t('about.philosophy.card2.title')}
                </h3>
                <p className="mt-6 text-body leading-relaxed text-[var(--text-secondary)] text-start">
                  {t('about.philosophy.card2.description')}
                </p>
              </div>
              {/* Добавлен flex-wrap для корректного переноса длинных арабских бейджей */}
              <div className="mt-10 flex gap-3 flex-wrap">
                {card2Badges.map((badge: string) => (
                  <span 
                    key={badge} 
                    className="bg-[var(--color-accent)]/10 text-[var(--accent-primary)] px-3 py-1 text-meta font-bold uppercase tracking-widest rounded-sm"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            </div>
          </Reveal>

        </div>
      </div>
    </section>
  );
};

export default AboutPhilosophySection;