// src/marketing/components/security/SecurityHeroSection.tsx
import React, { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import PathCrumb from '../platform/primitives/PathCrumb';

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const SecurityHeroSection: React.FC = () => {
  const { t, i18n } = useTranslation('security');
  const isRTL = i18n.language === 'ar';
  const prefersReduced = useReducedMotion();

  const layers = t('hero.layers', { returnObjects: true }) as string[];

  return (
    <section
      data-header-theme="light"
      className="relative flex min-h-[100dvh] items-center overflow-hidden bg-[var(--bg-base)]"
    >
      {/* ── Ambient glows ────────────────────────────────────────────── */}
      <div
        // RTL FIX: -left-1/4 заменен на -start-1/4
        className="pointer-events-none absolute -start-1/4 top-1/4 h-[800px] w-[800px] rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(200,107,82,0.06) 0%, rgba(200,107,82,0.02) 40%, transparent 70%)',
          filter: 'blur(40px)',
        }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -bottom-1/4 -end-1/4 h-[700px] w-[700px] rounded-full"
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
                root={t('hero.pathRoot')}
                leaf={t('hero.pathLeaf')}
              />
            </motion.div>

            <motion.h1
              className="mt-5 font-serif text-display text-[var(--text-primary)] whitespace-pre-line"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.12, ease }}
            >
              {t('hero.title')}
            </motion.h1>

            <motion.div
              className="mt-7 space-y-5"
              style={{ maxWidth: 620 }}
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
            >
              <p className="text-body leading-relaxed text-[var(--text-secondary)]">
                {t('hero.subtitle')}
              </p>
              <p className="text-body leading-relaxed text-[var(--text-muted)]">
                {t('hero.description')}
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
              <VideoWithLayersOverlay layers={layers} isRTL={isRTL} t={t} />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// VideoWithLayersOverlay
// ─────────────────────────────────────────────────────────────────────────────

interface VideoWithLayersOverlayProps {
  layers: string[];
  isRTL: boolean;
  t: any;
}

const VideoWithLayersOverlay: React.FC<VideoWithLayersOverlayProps> = ({ layers, isRTL, t }) => {
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
      className="relative w-full overflow-hidden rounded-2xl border border-[var(--border-color)] bg-[var(--color-dark)]"
      style={{
        maxWidth: 560,
        aspectRatio: '4 / 5',
        boxShadow:
          '0 20px 60px -20px rgba(26,25,23,0.25), 0 8px 20px -12px rgba(26,25,23,0.15)',
      }}
    >
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

      <AnimatePresence>
        {firstPlayComplete && (
          <motion.div
            className="absolute inset-0 flex items-center justify-center p-8 lg:p-10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, delay: 0.4, ease }}
          >
            <SecurityLayersStackDark layers={layers} isRTL={isRTL} t={t} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Security Layers Stack
// ─────────────────────────────────────────────────────────────────────────────

interface SecurityLayersStackDarkProps {
  layers: string[];
  isRTL: boolean;
  t: any;
}

const SecurityLayersStackDark: React.FC<SecurityLayersStackDarkProps> = ({ layers, isRTL, t }) => {
  return (
    <div className="relative w-full max-w-[420px]">
      {/* RTL FIX: left-0 заменен на start-0 */}
      <div
        className="absolute start-0 top-0 h-full w-[2px]"
        style={{
          background:
            'linear-gradient(180deg, transparent 0%, rgba(200,107,82,0.8) 20%, rgba(200,107,82,0.8) 80%, transparent 100%)',
        }}
      />

      <motion.p
        // RTL FIX: pl-7 заменен на ps-7
        className="mb-8 ps-7 text-eyebrow uppercase text-[rgba(250,248,245,0.75)]"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        style={{
          textShadow: '0 2px 12px rgba(0,0,0,0.5)',
        }}
      >
        {t('hero.layersTitle')}
      </motion.p>

      <ol className="space-y-5 ps-7">
        {layers.map((label, i) => (
          <motion.li
            key={label}
            className="flex items-baseline gap-5"
            initial={{ opacity: 0, x: isRTL ? -8 : 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: 0.45,
              delay: 0.6 + i * 0.08,
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            <span
              className="w-8 text-body-sm font-medium tabular-nums text-[rgba(200,107,82,1)]"
              style={{
                textShadow: '0 2px 8px rgba(0,0,0,0.6)',
              }}
            >
              0{i + 1}
            </span>
            <span
              className="font-serif text-h2 italic text-[rgba(250,248,245,1)] text-h1"
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