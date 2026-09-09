import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react"; // RTL FIX: Замена инлайн SVG на компонент Lucide

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  
  return (
    // RTL FIX: last:border-b-0 убирает лишнюю линию у последнего элемента
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        // RTL FIX: text-left заменен на text-start для корректного выравнивания в арабском
        className="flex w-full items-start justify-between gap-4 py-5 text-start"
      >
        <span className="text-body-sm font-medium leading-6 text-[var(--text-primary)]">
          {question}
        </span>
        {/* Поворот на 45 градусов превращает плюс в крестик. Это универсальный паттерн, не требующий инверсии для RTL */}
        <Plus
          className="mt-0.5 shrink-0 text-[var(--text-muted)] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
          size={16}
          strokeWidth={1.5}
          aria-hidden="true"
        />
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 300 : 0, opacity: open ? 1 : 0 }}
      >
        <p className="pb-5 text-body-sm leading-7 text-[var(--text-secondary)] text-start">
          {answer}
        </p>
      </div>
    </div>
  );
}

const DemoFaqSection: React.FC = () => {
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const itemsRaw = t("demo.faq.items", { returnObjects: true });
  const items = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="mt-12">
      <p className="eyebrow text-start">{t("demo.faq.eyebrow")}</p>
      <h2 className="text-h2 !mt-4 text-start">
        {t("demo.faq.title")}
      </h2>
      <div className="mt-8 rounded-xl border border-[var(--border-color)] bg-white px-6 py-2">
        {items.map((item) => (
          // RTL FIX: Стабильный key по id вместо question
          <FaqItem key={item.id} question={item.question} answer={item.answer} />
        ))}
      </div>
    </section>
  );
};

export default DemoFaqSection;