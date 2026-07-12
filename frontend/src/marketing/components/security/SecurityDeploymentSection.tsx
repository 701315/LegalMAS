// src/marketing/components/security/SecurityDeploymentSection.tsx

import React from 'react';
import { Server, Cloud, GitBranch } from 'lucide-react';
import Reveal from '../../motion/Reveal';
import { deploymentContent, deploymentModels } from './content/securityContent';
import type { DeploymentModel } from './content/securityContent';

const DEPLOYMENT_ICONS: Record<string, React.ReactNode> = {
  'On-Premise': <Server className="h-5 w-5" />,
  'Private Cloud': <Cloud className="h-5 w-5" />,
  Hybrid: <GitBranch className="h-5 w-5" />,
};

const SecurityDeploymentSection: React.FC = () => {
  return (
    <section className="bg-[var(--bg-surface)] py-24 lg:py-32">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <p className="eyebrow">{deploymentContent.eyebrow}</p>
            <h2 className="section-title">{deploymentContent.title}</h2>
            <p className="section-desc">{deploymentContent.description}</p>
          </div>
        </Reveal>

        <div className="mt-14 grid gap-5 lg:mt-16 lg:grid-cols-3">
          {deploymentModels.map((model, i) => (
            <Reveal key={model.title} delay={i * 0.1}>
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
  const icon = DEPLOYMENT_ICONS[model.title] ?? null;

  return (
    <div className="card-surface card-surface-hover group flex h-full flex-col p-7 lg:p-8">
      <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--bg-base)] text-[var(--text-secondary)] transition-colors duration-200 group-hover:border-[var(--color-accent)]/30 group-hover:text-[var(--color-accent)]">
        {icon}
      </div>

      <h3 className="mt-5 font-serif text-[1.375rem] leading-[1.2] tracking-[-0.02em] text-[var(--text-primary)]">
        {model.title}
      </h3>

      <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[var(--text-secondary)]">
        {model.description}
      </p>

      <div className="my-5 h-px bg-[var(--color-border)]" />

      <ul className="flex-1 space-y-3">
        {model.features.map((feature) => (
          <li key={feature} className="flex items-start gap-3">
            <span className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
            <span className="text-[0.875rem] leading-[1.65] text-[var(--text-secondary)]">{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-6 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--bg-base)] px-4 py-3">
        <ArchitectureSketch type={model.title} />
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Mini Architecture Sketch
// ─────────────────────────────────────────────────────────────────────────────

const ArchitectureSketch: React.FC<{ type: string }> = ({ type }) => {
  const n = 'rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--bg-card)] px-2.5 py-1 text-[0.6875rem] font-medium text-[var(--text-secondary)]';
  const h = 'h-px w-4 bg-[var(--color-faint)]';
  const v = 'mx-auto h-3 w-px bg-[var(--color-faint)]';

  if (type === 'On-Premise') {
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

  if (type === 'Private Cloud') {
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


