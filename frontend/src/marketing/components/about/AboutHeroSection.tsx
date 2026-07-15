import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import PathCrumb from '../platform/primitives/PathCrumb';

/**
 * AboutHeroSection — центрированный манифест.
 * Типографика и стили текста полностью соответствуют стандарту SecurityHeroSection.
 */

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const AboutHeroSection: React.FC = () => {
  const prefersReduced = useReducedMotion();

  return (
    <section
      data-header-theme="light"
      className="relative flex min-h-[80dvh] items-center overflow-hidden bg-[var(--bg-base)]"
    >
      {/* ── Ambient glows (из Security Hero) ─────────────────────────── */}
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
            <PathCrumb root="О нас" leaf="Что мы делаем" />
          </motion.div>

          {/* Заголовок — размер в точности как в Security Hero */}
          <motion.h1
            className="mt-8 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[var(--text-primary)] max-w-5xl"
            initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.12, ease }}
          >
            Мы автоматизируем подготовку информации,<br />
            <span 
              className="italic font-light"
              style={{ color: 'var(--color-accent)' }}
            >
              а не юридическое мышление
            </span>
          </motion.h1>

          {/* Описание — размер 1.0625rem / leading 1.7 как в Security Hero */}
          <motion.div
            className="mt-10 space-y-6"
            style={{ maxWidth: 680 }}
            initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
            animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.22, ease }}
          >
            <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
              Steloom берет на себя механику сбора и структурирования данных, 
              чтобы вы могли сосредоточиться на стратегии, рисках и принятии решений.
            </p>
            <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-muted)]">
              Мы создаем инструменты для юридических команд, которые ценят точность 
              и хотят масштабировать свою экспертизу, а не рутину.
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


