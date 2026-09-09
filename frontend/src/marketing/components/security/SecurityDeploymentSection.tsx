// src/marketing/components/security/SecurityDeploymentSection.tsx
import React from 'react';
import { Server, Cloud, GitBranch } from 'lucide-react';
import Reveal from '../../motion/Reveal';
import { useTranslation } from 'react-i18next';

interface DeploymentModel {
  id: 'onPremise' | 'privateCloud' | 'hybrid';
  title: string;
  description: string;
  features: string[];
}

// ИСПРАВЛЕНО: Привязка к стабильному ID, а не к переводимому заголовку
const DEPLOYMENT_ICONS: Record<string, React.ReactNode> = {
  onPremise: <Server className="h-5 w-5" />,
  privateCloud: <Cloud className="h-5 w-5" />,
  hybrid: <GitBranch className="h-5 w-5" />,
};

const SecurityDeploymentSection: React.FC = () => {
  const { t } = useTranslation('security');

  // Защитная проверка массива
  const modelsRaw = t('deployment.models', { returnObjects: true });
  const models = Array.isArray(modelsRaw) ? modelsRaw : [];

  return (
    <section className="bg-[var(--bg-surface)] py-24 lg:py-32">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <p className="eyebrow">{t('deployment.eyebrow')}</p>
            <h2 className="section-title">{t('deployment.title')}</h2>
            <p className="section-desc">{t('deployment.description')}</p>
          </div>
        </Reveal>

        <div className="mt-14 grid gap-5 lg:mt-16 lg:grid-cols-3">
          {models.map((model, i) => (
            <Reveal key={model.id} delay={i * 0.1}>
              <DeploymentCard model={model} />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Deployment Card
// ─────────────────────────────────────────────────────────────────────────────

const DeploymentCard: React.FC<{ model: DeploymentModel }> = ({ model }) => {
  const icon = DEPLOYMENT_ICONS[model.id] ?? null;

  return (
    <div className="card-surface card-surface-hover group flex h-full flex-col p-7 lg:p-8">
      <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-color)] bg-[var(--bg-base)] text-[var(--text-secondary)] transition-colors duration-200 group-hover:border-[var(--color-accent)]/30 group-hover:text-[var(--accent-primary)]">
        {icon}
      </div>

      <h3 className="mt-5 font-serif text-[1.375rem] leading-[1.2] tracking-[-0.02em] text-[var(--text-primary)]">
        {model.title}
      </h3>

      <p className="mt-3 text-body-sm leading-[1.7] text-[var(--text-secondary)]">
        {model.description}
      </p>

      <div className="my-5 h-px bg-[var(--color-border)]" />

      <ul className="flex-1 space-y-3">
        {model.features.map((feature, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
            <span className="text-sm leading-[1.65] text-[var(--text-secondary)]">{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-6 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--bg-base)] px-4 py-3">
        <ArchitectureSketch modelId={model.id} />
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Mini Architecture Sketch
// ─────────────────────────────────────────────────────────────────────────────

const ArchitectureSketch: React.FC<{ modelId: string }> = ({ modelId }) => {
  const n = 'rounded-[var(--radius-sm)] border border-[var(--border-color)] bg-[var(--bg-card)] px-2.5 py-1 text-[0.6875rem] font-medium text-[var(--text-secondary)]';
  const h = 'h-px w-4 bg-[var(--color-faint)]';
  const v = 'mx-auto h-3 w-px bg-[var(--color-faint)]';

  if (modelId === 'onPremise') {
    return (
      <div className="flex flex-col items-center gap-0">
        <div className={n}>Corporate Network</div>
        <div className={v} />
        <div className="flex items-center gap-0">
          <div className={n}>Steloom</div>
          <div className={h} />
          <div className={n}>DMS</div>
        </div>
        <div className={v} />
        <div className={n}>Storage</div>
      </div>
    );
  }

  if (modelId === 'privateCloud') {
    return (
      <div className="flex flex-col items-center gap-0">
        <div className={n}>VPC / Private Cloud</div>
        <div className={v} />
        <div className="flex items-center gap-0">
          <div className={n}>Steloom</div>
          <div className={h} />
          <div className={n}>Managed DB</div>
        </div>
        <div className={v} />
        <div className={n}>Object Storage</div>
      </div>
    );
  }

  // hybrid (fallback)
  return (
    <div className="flex flex-col items-center gap-0">
      <div className="flex items-center gap-0">
        <div className={n}>On-Prem</div>
        <div className={h} />
        <div className={n}>Cloud</div>
      </div>
      <div className={v} />
      <div className={n}>Steloom Gateway</div>
      <div className={v} />
      <div className="flex items-center gap-0">
        <div className={n}>Sensitive</div>
        <div className={h} />
        <div className={n}>Processing</div>
      </div>
    </div>
  );
};

export default SecurityDeploymentSection;