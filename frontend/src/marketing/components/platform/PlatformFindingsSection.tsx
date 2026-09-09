import React from "react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";
import FindingsDiagram from "./diagrams/FindingsDiagram";

const PlatformFindingsSection: React.FC = () => {
  // Инициализация i18n
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массивов из i18n
  const paragraphsRaw = t("platform.findings.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  const chainRaw = t("platform.findings.chain", { returnObjects: true });
  const chain = Array.isArray(chainRaw) ? chainRaw : [];

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
        <div className="grid gap-14 lg:grid-cols-12 lg:gap-16 lg:items-center">
          {/* ── Left: eyebrow + title + текст ────────────────────────── */}
          <Reveal className="lg:col-span-6">
            <div className="max-w-xl">
              <div className="eyebrow text-start">{t("platform.findings.eyebrow")}</div>

              <h2 className="mt-4 text-h1 text-start">
                {t("platform.findings.title")}
              </h2>

              <div className="mt-7 space-y-5">
                {paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-body text-start"
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>

          {/* ── Right: FindingsDiagram ───────────────────────────────── */}
          <Reveal className="lg:col-span-6" delay={0.12}>
            {/* Передаем безопасный массив chain в диаграмму */}
            <FindingsDiagram chain={chain} />
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default PlatformFindingsSection;