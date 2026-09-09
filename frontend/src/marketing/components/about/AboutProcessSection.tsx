import React from 'react';
import { useTranslation } from 'react-i18next';
import Reveal from '../../motion/Reveal';

const AboutProcessSection: React.FC = () => {
  // Инициализация i18n (isRTL не нужен, так как используем логические CSS-свойства Tailwind)
  const { t } = useTranslation('marketing');

  // Защита от сбоев при получении массива из i18n
  const stepsRaw = t('about.process.steps', { returnObjects: true });
  const steps = Array.isArray(stepsRaw) ? stepsRaw : [];

  return (
    <section className="relative py-40 lg:py-52 overflow-hidden border-y border-[var(--border-color)]">
      {/* ── Video Background ───────────────────────────────────────── */}
      <div className="absolute inset-0 z-0">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="h-full w-full object-cover"
        >
          <source src="/video/hero-about.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-black/80 backdrop-blur-[1px]" />
      </div>

      {/* ── Content ────────────────────────────────────────────────── */}
      <div 
        className="relative z-10 mx-auto w-full px-6 lg:px-8" 
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12 lg:gap-20">
          {steps.map((step, i) => (
            <Reveal key={step.label || i}>
              <div className="relative">
                <div className="flex items-center gap-3 mb-6">
                  <span className="text-meta font-bold tabular-nums text-[var(--accent-primary)] brightness-150">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div className="h-px w-6 bg-white/20" />
                  <p className="eyebrow !mb-0 block uppercase text-white/40 tracking-[0.2em] text-[10px]">
                    {step.label}
                  </p>
                </div>
                
                <h3 className="font-serif text-2xl italic mb-4 tracking-tight text-white/90">
                  {step.title}
                </h3>
                
                <p className="text-body-sm leading-[1.7] text-white/50 font-light max-w-[280px]">
                  {step.desc}
                </p>

                {/* Логическое свойство -end-10 автоматически работает и для LTR, и для RTL */}
                {i < 3 && (
                  <div className="hidden lg:block absolute top-1/2 -end-10 w-12 h-px bg-white/10" />
                )}
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
};

export default AboutProcessSection;