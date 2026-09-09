// src/marketing/components/home/FaqSection.tsx
import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";

interface FaqItemProps {
  q: string;
  a: string;
}

function FaqItem({ q, a }: FaqItemProps) {
  const [open, setOpen] = useState(false);
  
  return (
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        // text-start автоматически прижимает текст вправо в RTL
        className="flex w-full items-start justify-between gap-4 py-5 text-start transition-colors hover:bg-[var(--bg-base)]"
      >
        <span className="text-body-sm font-medium leading-relaxed text-[var(--text-primary)]">
          {q}
        </span>
        <span
          className="mt-1 shrink-0 text-[var(--text-muted)] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 300 : 0, opacity: open ? 1 : 0 }}
      >
        {/* pe-8 (padding-end) автоматически создает отступ справа в LTR и слева в RTL */}
        <p className="pb-6 pe-8 text-body-sm leading-relaxed text-[var(--text-secondary)]">
          {a}
        </p>
      </div>
    </div>
  );
}

const FaqSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");
  // isRTL используется здесь для разворота иконки ArrowRight
  const isRTL = i18n.language === "ar";

  const faq = t("home.faq", { returnObjects: true }) as {
    eyebrow: string;
    title: string;
    description: string;
    contactLabel: string;
    contactHref: string;
    items: { q: string; a: string }[];
  };

  return (
    <section className="bg-[var(--bg-surface)] py-20 lg:py-28" data-header-theme="light">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-[0.4fr_0.6fr] items-start">
          <div className="sticky top-32">
            <span className="eyebrow">{faq.eyebrow}</span>
            <h2 className="text-h2 text-[var(--text-primary)] whitespace-pre-line">
              {faq.title}
            </h2>
            <a
              href={faq.contactHref}
              className="cta-link mt-8 inline-flex items-center gap-2"
            >
              {faq.contactLabel}
              <ArrowRight
                className="h-3.5 w-3.5"
                style={{
                  transform: isRTL ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s ease",
                }}
              />
            </a>
          </div>

          <div className="flex flex-col">
            {faq.items.map((item, index) => (
              <FaqItem key={index} q={item.q} a={item.a} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default FaqSection;