// src/marketing/components/security/SecurityCapabilitiesSection.tsx

import React from 'react';
import Reveal from '../../motion/Reveal';
import { capabilitiesContent, capabilities } from './content/securityContent';
import type { SecurityCapability } from './content/securityContent';

const SecurityCapabilitiesSection: React.FC = () => {
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
            <h2 className="section-title">{capabilitiesContent.title}</h2>
            <p className="section-desc">{capabilitiesContent.description}</p>
          </div>
        </Reveal>

        {/* ── Capability blocks ──────────────────────────────────────── */}
        <div className="mt-16 space-y-20 lg:mt-20 lg:space-y-28">
          {capabilities.map((cap, i) => (
            <CapabilityBlock key={cap.label} capability={cap} index={i} />
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
}

const CapabilityBlock: React.FC<CapabilityBlockProps> = ({ capability, index }) => {
  const isTextLeft = capability.layout === 'left';

  return (
    <Reveal>
      <div className="grid items-center gap-8 lg:grid-cols-12 lg:gap-12">
        {/* ── Text column ────────────────────────────────────────────── */}
        <div className={`lg:col-span-7 ${isTextLeft ? '' : 'lg:order-2'}`}>
          <div className="flex items-center gap-3">
            <span className="text-[0.75rem] font-medium tabular-nums text-[var(--color-accent)]">
              {String(index + 1).padStart(2, '0')}
            </span>
            <p className="eyebrow !mb-0">{capability.label}</p>
          </div>

          <h3 className="mt-4 font-serif text-[clamp(1.5rem,3vw,2rem)] leading-[1.15] tracking-[-0.02em] text-[var(--text-primary)]">
            {capability.title}
          </h3>

          {capability.subtitle && (
            <p className="mt-3 text-[0.9375rem] font-medium text-[var(--text-primary)]">
              {capability.subtitle}
            </p>
          )}

          <div className="mt-5 space-y-4" style={{ maxWidth: 620 }}>
            {capability.paragraphs.map((p, i) => (
              <p key={i} className="text-[0.9375rem] leading-[1.7] text-[var(--text-secondary)]">
                {p}
              </p>
            ))}
          </div>
        </div>

        {/* ── Bullet card column ─────────────────────────────────────── */}
        <div className={`lg:col-span-5 ${isTextLeft ? '' : 'lg:order-1'}`}>
          <BulletCard
            bullets={capability.bullets}
            variant={index % 3 === 0 ? 'bordered' : index % 3 === 1 ? 'filled' : 'editorial'}
          />
        </div>
      </div>

      {index < capabilities.length - 1 && (
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
  const styles: Record<typeof variant, string> = {
    bordered: 'card-surface p-6 lg:p-8',
    filled: 'rounded-2xl border border-[var(--color-border)] bg-[var(--bg-surface)] p-6 lg:p-8',
    editorial: 'border-l-2 border-[var(--color-border)] pl-6 lg:pl-8',
  };

  return (
    <div className={styles[variant]}>
      {variant !== 'editorial' && (
        <p className="mb-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
          Ключевые принципы
        </p>
      )}
      <ul className="space-y-3.5">
        {bullets.map((bullet) => (
          <li key={bullet} className="flex items-start gap-3.5">
            <span className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
            <span className="text-[0.9375rem] leading-[1.7] text-[var(--text-secondary)]">{bullet}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default SecurityCapabilitiesSection;


