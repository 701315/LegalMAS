// src/marketing/components/security/SecurityCapabilitiesSection.tsx
import React from 'react';
import Reveal from '../../motion/Reveal';
import { useTranslation } from 'react-i18next';

interface SecurityCapability {
  label: string;
  title: string;
  subtitle?: string;
  paragraphs: string[];
  bullets: string[];
  layout: 'left' | 'right';
}

const SecurityCapabilitiesSection: React.FC = () => {
  const { t, i18n } = useTranslation('security');
  const isRTL = i18n.language === 'ar';

  const capabilitiesContent = {
    eyebrow: t('capabilities.eyebrow'),
    title: t('capabilities.title'),
    description: t('capabilities.description'),
  };

  // 🛡️ ЗАЩИТНАЯ ПРОВЕРКА: гарантируем, что это массив, прежде чем вызывать .map()
  const capabilitiesRaw = t('capabilities.items', { returnObjects: true });
  const capabilities = Array.isArray(capabilitiesRaw) 
    ? capabilitiesRaw 
    : [];

  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <Reveal>
          <div className="max-w-2xl">
            <p className="eyebrow">{capabilitiesContent.eyebrow}</p>
            <h2 className="text-h2">{capabilitiesContent.title}</h2>
            <p className="section-desc">{capabilitiesContent.description}</p>
          </div>
        </Reveal>

        {/* ── Capability blocks ──────────────────────────────────────── */}
        <div className="mt-16 space-y-20 lg:mt-20 lg:space-y-28">
          {capabilities.map((cap, i) => (
            <CapabilityBlock
              key={cap.label}
              capability={cap}
              index={i}
              isRTL={isRTL}
              isLast={i === capabilities.length - 1}
            />
          ))}
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Capability Block
// ─────────────────────────────────────────────────────────────────────────────

interface CapabilityBlockProps {
  capability: SecurityCapability;
  index: number;
  isRTL: boolean;
  isLast: boolean;
}

const CapabilityBlock: React.FC<CapabilityBlockProps> = ({
  capability,
  index,
  isRTL,
  isLast,
}) => {
  const isTextVisuallyLeft = capability.layout === 'left';
  
  // Инвертируем order для RTL, чтобы сохранить задуманный визуальный лейаут
  const textOrderClass = isTextVisuallyLeft
    ? isRTL ? 'lg:order-2' : 'lg:order-1'
    : isRTL ? 'lg:order-1' : 'lg:order-2';
    
  const bulletOrderClass = isTextVisuallyLeft
    ? isRTL ? 'lg:order-1' : 'lg:order-2'
    : isRTL ? 'lg:order-2' : 'lg:order-1';

  return (
    <Reveal>
      <div className="grid items-center gap-8 lg:grid-cols-12 lg:gap-12">
        {/* ── Text column ────────────────────────────────────────────── */}
        <div className={`lg:col-span-7 ${textOrderClass}`}>
          <div className="flex items-center gap-3">
            <span className="text-meta font-medium tabular-nums text-[var(--accent-primary)]">
              {String(index + 1).padStart(2, '0')}
            </span>
            <p className="eyebrow !mb-0">{capability.label}</p>
          </div>

          <h3 className="mt-4 font-serif text-h2 text-[var(--text-primary)]">
            {capability.title}
          </h3>

          {capability.subtitle && (
            <p className="mt-3 text-body-sm font-medium text-[var(--text-primary)]">
              {capability.subtitle}
            </p>
          )}

          <div className="mt-5 space-y-4" style={{ maxWidth: 620 }}>
            {capability.paragraphs.map((p, i) => (
              <p key={i} className="text-body-sm leading-relaxed text-[var(--text-secondary)]">
                {p}
              </p>
            ))}
          </div>
        </div>

        {/* ── Bullet card column ─────────────────────────────────────── */}
        <div className={`lg:col-span-5 ${bulletOrderClass}`}>
          <BulletCard
            bullets={capability.bullets}
            variant={
              index % 3 === 0 ? 'bordered' : index % 3 === 1 ? 'filled' : 'editorial'
            }
          />
        </div>
      </div>

      {!isLast && (
        <div className="mt-20 flex justify-center lg:mt-28">
          <div className="h-px w-16 bg-[var(--color-border)]" />
        </div>
      )}
    </Reveal>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Bullet Card
// ─────────────────────────────────────────────────────────────────────────────

interface BulletCardProps {
  bullets: string[];
  variant: 'bordered' | 'filled' | 'editorial';
}

const BulletCard: React.FC<BulletCardProps> = ({ bullets, variant }) => {
  const { t } = useTranslation('security');

  // RTL FIX: border-l-2, pl-6, pl-8 заменены на border-s-2, ps-6, ps-8
  const styles: Record<typeof variant, string> = {
    bordered: 'card-surface p-6 lg:p-8',
    filled: 'rounded-2xl border border-[var(--border-color)] bg-[var(--bg-surface)] p-6 lg:p-8',
    editorial: 'border-s-2 border-[var(--border-color)] ps-6 lg:ps-8',
  };

  return (
    <div className={styles[variant]}>
      {variant !== 'editorial' && (
        <p className="mb-5 text-meta">
          {t('capabilities.keyPrinciples')}
        </p>
      )}
      <ul className="space-y-3.5">
        {bullets.map((bullet, i) => (
          <li key={i} className="flex items-start gap-3.5">
            <span
              className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]"
              aria-hidden="true"
            />
            <span className="text-body-sm leading-relaxed text-[var(--text-secondary)]">
              {bullet}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default SecurityCapabilitiesSection;