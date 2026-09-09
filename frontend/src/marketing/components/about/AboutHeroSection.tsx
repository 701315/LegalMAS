// src/marketing/components/about/AboutHeroSection.tsx
import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import PathCrumb from '../platform/primitives/PathCrumb';

/**
 * AboutHeroSection — центрированный манифест.
 * Типографика и стили текста полностью соответствуют стандарту SecurityHeroSection.
 */
const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const AboutHeroSection: React.FC = () => {
  const { t } = useTranslation('marketing');
  const prefersReduced = useReducedMotion();

  return (
    <section
      data-header-theme="light"
      className="relative flex min-h-[80dvh] items-center overflow-hidden bg-[var(--bg-base)]"
    >
      {/* ── Ambient glows ─────────────────────────── */}
      {/* Примечание: left-1/2 + -translate-x-1/2 корректно центрируют элемент в любом направлении (LTR/RTL) */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[800px] w-[800px] rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(200,107,82,0.04) 0%, rgba(200,107,82,0.01) 40%, transparent 70%)',
          filter: 'blur(60px)',
        }}
        aria-hidden="true"
      />
      
      {/* Сетка фона */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(rgba(26,25,23,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(26,25,23,0.03) 1px, transparent 1px)
          `,
          backgroundSize: '80px 80px',
        }}
        aria-hidden="true"
      />

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div
        className="relative z-10 mx-auto w-full px-6 pb-24 pt-24 lg:px-8 lg:pb-32 lg:pt-32"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <div className="flex flex-col items-center text-center">
          
          {/* PathCrumb центрированный */}
          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05, ease }}
          >
            <PathCrumb root={t('about.hero.pathRoot')} leaf={t('about.hero.pathLeaf')} />
          </motion.div>

          {/* Заголовок — используем whitespace-pre-line вместо <br /> */}
          <motion.h1
            className="mt-8 text-display max-w-5xl whitespace-pre-line"
            initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.12, ease }}
          >
            {t('about.hero.title')}
          </motion.h1>

          {/* Описание */}
          <motion.div
            className="mt-10 space-y-6"
            style={{ maxWidth: 680 }}
            initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.22, ease }}
          >
            <p className="text-body leading-[1.7] text-[var(--text-secondary)]">
              {t('about.hero.description1')}
            </p>
            <p className="text-body leading-[1.7] text-[var(--text-muted)]">
              {t('about.hero.description2')}
            </p>
          </motion.div>

          {/* Декоративный якорь внизу */}
          <motion.div 
            className="mt-20 h-24 w-px bg-[var(--color-accent)] opacity-20"
            initial={{ height: 0 }}
            animate={{ height: 96 }}
            transition={{ duration: 1, delay: 0.5, ease }}
          />
        </div>
      </div>
    </section>
  );
};

export default AboutHeroSection;