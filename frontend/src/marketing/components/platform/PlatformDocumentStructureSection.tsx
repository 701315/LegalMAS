import React from "react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";
import VerticalNodeChain from "./diagrams/VerticalNodeChain";

const PlatformDocumentStructureSection: React.FC = () => {
  // Инициализация i18n (i18n объект не нужен, так как RTL решается через CSS)
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массивов из i18n
  const paragraphsRaw = t("platform.structure.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  const bulletsRaw = t("platform.structure.bullets", { returnObjects: true });
  const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

  const chainRaw = t("platform.structure.chain", { returnObjects: true });
  const chain = Array.isArray(chainRaw) ? chainRaw : [];

  return (
    <section
      className="relative"
      style={{ background: "#FAF8F5" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-14 lg:grid-cols-12 lg:gap-16 lg:items-center">
          {/* ── Left: текст ─────────────────────────────────────────────── */}
          <Reveal className="lg:col-span-7">
            <div className="max-w-2xl">
              <div className="eyebrow text-start">{t("platform.structure.eyebrow")}</div>

              <h2 className="mt-4 text-h1 text-start">
                {t("platform.structure.title")}
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

              {/* RTL FIX: border-l заменен на border-s, pl-6 заменен на ps-6 */}
              <div className="mt-10 border-s border-[var(--border-color)] ps-6">
                <div className="text-meta text-start">
                  {t("platform.structure.bulletsLabel")}
                </div>
                <ul className="mt-4 space-y-3">
                  {bullets.map((bullet, i) => (
                    <li
                      key={i} // Используем индекс, так как это массив строк из i18n
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
            </div>
          </Reveal>

          {/* ── Right: вертикальная схема структуры ─────────────────────── */}
          <div className="lg:col-span-5">
            <Reveal delay={0.15}>
              <div className="mx-auto" style={{ maxWidth: 380 }}>
                <VerticalNodeChain
                  nodes={chain}
                  size="sm"
                />
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformDocumentStructureSection;