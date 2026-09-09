import React from "react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";
import FlowSchema from "./diagrams/FlowSchema";

const PlatformWorkflowSection: React.FC = () => {
  // RTL FIX: Оставляем только t, так как i18n здесь не используется (RTL решается через CSS)
  const { t } = useTranslation("marketing");
  
  // RTL FIX: Защита от сбоев при получении массивов из i18n
  const stepsRaw = t("platform.workflow.steps", { returnObjects: true });
  const steps = Array.isArray(stepsRaw) ? stepsRaw : [];

  const paragraphsRaw = t("platform.workflow.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  const bulletsRaw = t("platform.workflow.bullets", { returnObjects: true });
  const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

  return (
    <section
      className="relative"
      style={{ background: "#F3F0EB" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <Reveal>
          <div className="max-w-3xl">
            <div className="eyebrow text-start">{t("platform.workflow.eyebrow")}</div>
            <h2 className="mt-4 text-h1 text-start">
              {t("platform.workflow.title")}
            </h2>
          </div>
        </Reveal>

        {/* ── Flow schema ─────────────────────────────────────────────── */}
        <div className="mt-14 lg:mt-16">
          <FlowSchema steps={steps} />
        </div>

        {/* ── Split: текст + editorial-выноска bullets ────────────────── */}
        <div className="mt-16 grid gap-10 lg:mt-20 lg:grid-cols-12 lg:gap-12 lg:items-start">
          {/* Левая колонка: текст */}
          <Reveal className="lg:col-span-7">
            <div className="space-y-5" style={{ maxWidth: 640 }}>
              {paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="text-body text-start"
                >
                  {p}
                </p>
              ))}
            </div>
          </Reveal>

          {/* Правая колонка: editorial-выноска с bullets */}
          <Reveal delay={0.1} className="lg:col-span-5">
            {/* RTL FIX: border-l заменен на border-s, pl-6 заменен на ps-6 */}
            <div className="border-s border-[var(--border-color)] ps-6">
              <div className="text-meta text-start">
                {t("platform.workflow.bulletsLabel")}
              </div>
              <ul className="mt-4 space-y-3">
                {bullets.map((bullet, i) => (
                  <li
                    key={i} // RTL FIX: Используем индекс вместо текста для стабильного ключа
                    className="flex items-start gap-3 text-[var(--text-secondary)] text-start"
                  >
                    <span
                      className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]"
                      aria-hidden="true"
                    />
                    <span className="text-body-sm leading-normal">
                      {bullet}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default PlatformWorkflowSection;