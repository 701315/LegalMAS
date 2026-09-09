import React, { useState } from "react";
import { useTranslation } from "react-i18next";

const DemoFormSection: React.FC = () => {
  const { t } = useTranslation("marketing");
  
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [useCase, setUseCase] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // RTL FIX: Локализация тела письма в зависимости от выбранного языка
    const subject = encodeURIComponent(t("demo.form.submit"));
    const body = encodeURIComponent(
      `${t("demo.form.emailBody.name")}: ${name}\n` +
      `${t("demo.form.emailBody.company")}: ${company}\n` +
      `${t("demo.form.emailBody.email")}: ${email}\n\n` +
      `${t("demo.form.emailBody.useCase")}:\n${useCase}`
    );
    
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const asideItemsRaw = t("demo.aside.items", { returnObjects: true });
  const asideItems = Array.isArray(asideItemsRaw) ? asideItemsRaw : [];

  return (
    <section className="mt-12 grid gap-6 lg:grid-cols-[1fr_0.75fr] lg:items-start">
      {/* Форма */}
      <div className="rounded-2xl border border-[var(--border-color)] bg-white p-7 lg:p-9">
        <h2 className="font-serif text-2xl tracking-[-0.03em] text-[var(--text-primary)] text-start">
          {t("demo.form.title")}
        </h2>
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)] text-start">
          {t("demo.form.subtitle")}
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)] text-start">
              {t("demo.form.fields.name")}
            </label>
            <input 
              type="text" 
              required 
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("demo.form.placeholders.name")}
              className="input-base text-start" 
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)] text-start">
              {t("demo.form.fields.company")}
            </label>
            <input 
              type="text" 
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={t("demo.form.placeholders.company")}
              className="input-base text-start" 
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)] text-start">
              {t("demo.form.fields.email")}
            </label>
            <input 
              type="email" 
              required 
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("demo.form.placeholders.email")}
              className="input-base text-start" 
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)] text-start">
              {t("demo.form.fields.useCase")}
            </label>
            <textarea 
              required 
              rows={5} 
              value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              placeholder={t("demo.form.placeholders.useCase")}
              className="input-base resize-none text-start" 
            />
          </div>
          <p className="text-xs text-[var(--text-muted)] text-start">
            {t("demo.form.note")}
          </p>
          <button type="submit" className="cta-primary w-full sm:w-auto">
            {t("demo.form.submit")}
          </button>
        </form>
      </div>

      {/* Aside */}
      <aside className="rounded-2xl border border-[var(--border-color)] bg-[var(--bg-surface)] p-7">
        <h3 className="font-serif text-xl tracking-[-0.02em] text-[var(--text-primary)] text-start">
          {t("demo.aside.title")}
        </h3>
        <ul className="mt-6 space-y-3">
          {asideItems.map((item) => (
            <li key={item.id} className="flex items-start gap-2.5 text-sm leading-6 text-[var(--text-secondary)] text-start">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[#A8A29E]" />
              {item.text}
            </li>
          ))}
        </ul>
        <p className="mt-8 text-xs text-[var(--text-muted)] text-start">
          {t("demo.aside.time")}
        </p>
      </aside>
    </section>
  );
};

export default DemoFormSection;