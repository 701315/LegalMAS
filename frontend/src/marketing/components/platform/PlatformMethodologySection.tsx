import React from "react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";
import VerticalNodeChain from "./diagrams/VerticalNodeChain";

const PlatformMethodologySection: React.FC = () => {
  // Инициализация i18n (i18n объект не нужен, так как RTL решается через CSS)
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массивов из i18n
  const paragraphsRaw = t("platform.methodology.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  const chainRaw = t("platform.methodology.chain", { returnObjects: true });
  const chain = Array.isArray(chainRaw) ? chainRaw : [];

  return (
    <section
      className="relative"
      style={{ background: "#FAF8F5" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-16 lg:grid-cols-12 lg:gap-20 lg:items-center">
          {/* ── Left: eyebrow + заголовок + lead-in + текст ──────────── */}
          <Reveal className="lg:col-span-7">
            <div className="max-w-2xl">
              <div className="eyebrow text-start">{t("platform.methodology.eyebrow")}</div>

              <h2 className="mt-4 text-h1 text-start">
                {t("platform.methodology.title")}
              </h2>

              {/* Lead-in — короткое tagline-предложение перед основным текстом */}
              <p
                className="mt-6 font-serif text-h3 italic leading-[1.5] text-[var(--text-primary)] text-start"
                style={{ maxWidth: 560 }}
              >
                {t("platform.methodology.leadIn")}
              </p>

              <div className="mt-6 space-y-5" style={{ maxWidth: 620 }}>
                {paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-body leading-[1.75] text-[var(--text-secondary)] text-start"
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>

          {/* ── Right: VerticalNodeChain (size="md") ─────────────────── */}
          <div className="lg:col-span-5">
            <Reveal delay={0.15}>
              <div className="mx-auto" style={{ maxWidth: 420 }}>
                {/* Передаем безопасный массив chain в диаграмму */}
                <VerticalNodeChain
                  nodes={chain}
                  size="md"
                />
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformMethodologySection;