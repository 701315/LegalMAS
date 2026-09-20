interface FindingsDiagramProps {
  chain?: any[];
}
import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

interface StepItem {
  num: string;
  titleKey: string;
  subKey: string;
  fallbackTitle: string;
  fallbackSub: string;
  isHighlight?: boolean;
}

const STEPS: StepItem[] = [
  {
    num: "01",
    titleKey: "platform.findingsDiagram.step1Title",
    subKey: "platform.findingsDiagram.step1Sub",
    fallbackTitle: "Document",
    fallbackSub: "FILE",
  },
  {
    num: "02",
    titleKey: "platform.findingsDiagram.step2Title",
    subKey: "platform.findingsDiagram.step2Sub",
    fallbackTitle: "Clause",
    fallbackSub: "SECTION",
  },
  {
    num: "03",
    titleKey: "platform.findingsDiagram.step3Title",
    subKey: "platform.findingsDiagram.step3Sub",
    fallbackTitle: "Risk",
    fallbackSub: "CATEGORY",
  },
  {
    num: "04",
    titleKey: "platform.findingsDiagram.step4Title",
    subKey: "platform.findingsDiagram.step4Sub",
    fallbackTitle: "Severity",
    fallbackSub: "LEVEL",
  },
  {
    num: "05",
    titleKey: "platform.findingsDiagram.step5Title",
    subKey: "platform.findingsDiagram.step5Sub",
    fallbackTitle: "Source Link",
    fallbackSub: "VERIFIABLE",
    isHighlight: true,
  },
];

const FindingsDiagram: React.FC<FindingsDiagramProps> = () => {
  const shouldReduceMotion = useReducedMotion();
  const { t } = useTranslation("marketing");

  return (
    <div className="w-full py-4">
      {/* ── ГОРИЗОНТАЛЬНЫЙ ЦЕПНОЙ СПИСОК ИЗ 5 ОДИНАКОВЫХ КАРТОЧЕК ─────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 lg:flex-nowrap">
        {STEPS.map((step, idx) => {
          const title = t(step.titleKey, step.fallbackTitle);
          const sub = t(step.subKey, step.fallbackSub);

          return (
            <React.Fragment key={step.num}>
              {/* Карточка со строгими фиксированными габаритами */}
              <motion.div
                initial={shouldReduceMotion ? undefined : { opacity: 0, y: 12 }}
                whileInView={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: idx * 0.08, ease: EASE }}
                className={`flex h-32 w-full flex-1 flex-col justify-between rounded-xl border p-3.5 text-center transition-all duration-300 min-w-[105px] max-w-[130px] ${
                  step.isHighlight
                    ? "border-[var(--accent-primary)] bg-[#F5EBE7]/50 shadow-sm"
                    : "border-[var(--border-color)] bg-white shadow-sm"
                }`}
              >
                <div>
                  <div className="text-[10px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
                    LEVEL {step.num}
                  </div>
                  <div className="mt-1.5 text-xs font-bold leading-snug text-[var(--text-primary)]">
                    {title}
                  </div>
                </div>

                <div className="text-[9px] font-medium tracking-wider text-[var(--text-secondary)] uppercase line-clamp-1">
                  {sub}
                </div>
              </motion.div>

              {/* Стрелочка-переход между карточками */}
              {idx < STEPS.length - 1 && (
                <div className="hidden shrink-0 items-center justify-center text-gray-300 sm:flex">
                  <svg
                    className="h-4 w-4 text-[var(--text-muted)] opacity-40"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Подпись снизу */}
      <div className="mt-6 text-center text-meta text-[var(--text-muted)]">
        — {t("platform.findings.caption", "EVERY FINDING IS TRACEABLE FROM THE PRIMARY SOURCE TO THE CONCLUSION")} —
      </div>
    </div>
  );
};

export default FindingsDiagram;
