// src/marketing/components/security/SecurityHeroSection.tsx

import React, { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import { heroContent } from './content/securityContent';
import PathCrumb from '../platform/primitives/PathCrumb';

/**
 * SecurityHeroSection — светлый editorial hero.
 *
 * Правая колонка:
 *   • Видео (hero-security.mp4) играет в цикле как живой фон
 *   • После первого полного проигрывания — появляется полупрозрачное
 *     затемнение + список слоёв поверх
 */

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const SecurityHeroSection: React.FC = () => {
  const prefersReduced = useReducedMotion();

  return (
    <section
      data-header-theme="light"
      className="relative flex min-h-[100dvh] items-center overflow-hidden bg-[var(--bg-base)]"
    >
      {/* ── Ambient glows ────────────────────────────────────────────── */}
      <div
        className="pointer-events-none absolute -left-1/4 top-1/4 h-[800px] w-[800px] rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(200,107,82,0.06) 0%, rgba(200,107,82,0.02) 40%, transparent 70%)',
          filter: 'blur(40px)',
        }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -bottom-1/4 -right-1/4 h-[700px] w-[700px] rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(120,117,111,0.06) 0%, rgba(120,117,111,0.02) 40%, transparent 70%)',
          filter: 'blur(50px)',
        }}
        aria-hidden="true"
      />
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
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 40%, rgba(120,117,111,0.08) 100%)',
        }}
        aria-hidden="true"
      />

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div
        className="relative z-10 mx-auto w-full px-6 pb-24 pt-24 lg:px-8 lg:pb-32 lg:pt-32"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:items-center lg:gap-16">
          {/* ── Left: текст ──────────────────────────────────────────── */}
          <div className="lg:col-span-6">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb
                root={heroContent.pathRoot}
                leaf={heroContent.pathLeaf}
              />
            </motion.div>

            <motion.h1
              className="mt-5 font-serif text-[clamp(2.5rem,5vw,4rem)] leading-[1.05] tracking-[-0.03em] text-[var(--text-primary)]"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.12, ease }}
            >
              {heroContent.title.split('\n').map((line: string, i: number) => (
                <React.Fragment key={i}>
                  {i > 0 && <br />}
                  {line}
                </React.Fragment>
              ))}
            </motion.h1>

            <motion.div
              className="mt-7 space-y-5"
              style={{ maxWidth: 620 }}
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
            >
              <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                {heroContent.subtitle}
              </p>
              <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-muted)]">
                {heroContent.description}
              </p>
            </motion.div>
          </div>

          {/* ── Right: видео + список поверх ──────────────────────────── */}
          <div className="lg:col-span-6">
            <motion.div
              className="flex justify-center lg:justify-end"
              initial={prefersReduced ? undefined : { opacity: 0, y: 16 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.4, ease }}
            >
              <VideoWithLayersOverlay />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// VideoWithLayersOverlay — видео loops + список после первого проигрывания
// ─────────────────────────────────────────────────────────────────────────────

const VideoWithLayersOverlay: React.FC = () => {
  const prefersReduced = useReducedMotion();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [firstPlayComplete, setFirstPlayComplete] = useState(false);

  useEffect(() => {
    if (prefersReduced) {
      setFirstPlayComplete(true);
      return;
    }

    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      if (video.duration && video.currentTime >= video.duration - 0.1) {
        setFirstPlayComplete(true);
        video.removeEventListener('timeupdate', handleTimeUpdate);
      }
    };

    video.addEventListener('timeupdate', handleTimeUpdate);

    const fallbackTimer = setTimeout(() => {
      setFirstPlayComplete(true);
    }, 10000);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      clearTimeout(fallbackTimer);
    };
  }, [prefersReduced]);

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-dark)]"
      style={{
        maxWidth: 560,
        aspectRatio: '4 / 5',
        boxShadow:
          '0 20px 60px -20px rgba(26,25,23,0.25), 0 8px 20px -12px rgba(26,25,23,0.15)',
      }}
    >
      {/* ── Видео (loop) ─────────────────────────────────────────────── */}
      {!prefersReduced && (
        <video
          ref={videoRef}
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          className="absolute inset-0 h-full w-full object-cover"
          aria-hidden="true"
        >
          <source src="/video/hero-security.mp4" type="video/mp4" />
        </video>
      )}

      {/* ── Плотное затемнение (ПЛОТНЕЕ для читаемости) ─────────────── */}
      <AnimatePresence>
        {firstPlayComplete && (
          <motion.div
            className="absolute inset-0"
            style={{
              background:
                'linear-gradient(135deg, rgba(26,25,23,0.78) 0%, rgba(26,25,23,0.88) 100%)',
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.9, ease }}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* ── Список слоёв ─────────────────────────────────────────────── */}
      <AnimatePresence>
        {firstPlayComplete && (
          <motion.div
            className="absolute inset-0 flex items-center justify-center p-8 lg:p-10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, delay: 0.4, ease }}
          >
            <SecurityLayersStackDark />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Security Layers Stack — тёмная версия, увеличенный текст
// ─────────────────────────────────────────────────────────────────────────────

const LAYERS = ['Infrastructure', 'Data', 'Access', 'Processing', 'Audit'];

const SecurityLayersStackDark: React.FC = () => {
  return (
    <div className="relative w-full max-w-[420px]">
      {/* Vertical accent line — толще, ярче */}
      <div
        className="absolute left-0 top-0 h-full w-[2px]"
        style={{
          background:
            'linear-gradient(180deg, transparent 0%, rgba(200,107,82,0.8) 20%, rgba(200,107,82,0.8) 80%, transparent 100%)',
        }}
      />

      <motion.p
        className="mb-8 pl-7 text-[0.8125rem] uppercase tracking-[0.24em] text-[rgba(250,248,245,0.75)]"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        style={{
          textShadow: '0 2px 12px rgba(0,0,0,0.5)',
        }}
      >
        Пять слоёв защиты
      </motion.p>

      <ol className="space-y-5 pl-7">
        {LAYERS.map((label, i) => (
          <motion.li
            key={label}
            className="flex items-baseline gap-5"
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: 0.45,
              delay: 0.6 + i * 0.08,
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            <span
              className="w-8 text-[0.9375rem] font-medium tabular-nums text-[rgba(200,107,82,1)]"
              style={{
                textShadow: '0 2px 8px rgba(0,0,0,0.6)',
              }}
            >
              0{i + 1}
            </span>
            <span
              className="font-serif text-[2rem] italic leading-[1.15] text-[rgba(250,248,245,1)] lg:text-[2.25rem]"
              style={{
                textShadow: '0 2px 16px rgba(0,0,0,0.7)',
              }}
            >
              {label}
            </span>
          </motion.li>
        ))}
      </ol>
    </div>
  );
};

export default SecurityHeroSection;


