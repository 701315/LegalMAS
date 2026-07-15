import React from 'react';
import Reveal from '../../motion/Reveal';

const AboutPhilosophy: React.FC = () => {
  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
        <div className="grid md:grid-cols-2 gap-8 lg:gap-12">
          
          {/* Card 1: Infrastructure */}
          <Reveal>
            <div className="card-surface p-10 lg:p-12 flex flex-col h-full justify-between border-[var(--color-border)]">
              <div>
                <p className="eyebrow">Позиционирование</p>
                <h3 className="section-title text-3xl mt-4">Часть ежедневного процесса</h3>
                <p className="text-[0.9375rem] leading-[1.7] text-[var(--text-secondary)] mt-6">
                  Steloom не заменяет юриста, а становится инфраструктурой для его работы. 
                  Платформа классифицирует документы и готовит основу для профессионального review.
                </p>
              </div>
              <ul className="mt-10 space-y-3">
                {['Workflow Integration', 'Scale Intelligence'].map(tag => (
                  <li key={tag} className="flex items-center gap-3 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    <span className="h-1 w-1 rounded-full bg-[var(--color-accent)]" /> {tag}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          {/* Card 2: Output */}
          <Reveal>
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--bg-surface)] p-10 lg:p-12 flex flex-col h-full justify-between">
              <div>
                <p className="eyebrow">Подход</p>
                <h3 className="section-title text-3xl mt-4">Структурированная основа</h3>
                <p className="text-[0.9375rem] leading-[1.7] text-[var(--text-secondary)] mt-6">
                  Вместо разрозненных ответов вы получаете систему: DD-сетки по типам документов, 
                  findings с источниками и приоритизацию рисков.
                </p>
              </div>
              <div className="mt-10 flex gap-3">
                <span className="bg-[var(--color-accent)]/10 text-[var(--color-accent)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-sm">
                  Verified Output
                </span>
                <span className="bg-[var(--color-accent)]/10 text-[var(--color-accent)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-sm">
                  Evidence-Based
                </span>
              </div>
            </div>
          </Reveal>

        </div>
      </div>
    </section>
  );
};

export default AboutPhilosophy;


