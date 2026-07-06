// frontend/src/components/marketing/demo/DemoFormSection.tsx
import React, { useState } from "react";
import { demoContent } from "../../content/demoContent";

const DemoFormSection: React.FC = () => {
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [useCase, setUseCase] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Запрос демо Steloom");
    const body = encodeURIComponent(
      `Имя: ${name}\nКомпания: ${company}\nEmail: ${email}\n\nСценарий:\n${useCase}`
    );
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <section className="mt-12 grid gap-6 lg:grid-cols-[1fr_0.75fr] lg:items-start">

      {/* Форма */}
      <div className="rounded-2xl border border-[#E8E4DD] bg-white p-7 lg:p-9">
        <h2 className="font-serif text-2xl tracking-[-0.03em] text-[#1A1917]">
          {demoContent.form.title}
        </h2>
        <p className="mt-3 text-sm leading-7 text-[#78756F]">{demoContent.form.subtitle}</p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#78756F]">
              {demoContent.form.fields.name}
            </label>
            <input type="text" required value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={demoContent.form.placeholders.name}
              className="input-base" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#78756F]">
              {demoContent.form.fields.company}
            </label>
            <input type="text" value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={demoContent.form.placeholders.company}
              className="input-base" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#78756F]">
              {demoContent.form.fields.email}
            </label>
            <input type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={demoContent.form.placeholders.email}
              className="input-base" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#78756F]">
              {demoContent.form.fields.useCase}
            </label>
            <textarea required rows={5} value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              placeholder={demoContent.form.placeholders.useCase}
              className="input-base resize-none" />
          </div>
          <p className="text-xs text-[#A8A29E]">{demoContent.form.note}</p>
          <button type="submit" className="cta-primary">
            {demoContent.form.submit}
          </button>
        </form>
      </div>

      {/* Aside */}
      <aside className="rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7">
        <h3 className="font-serif text-xl tracking-[-0.02em] text-[#1A1917]">
          {demoContent.aside.title}
        </h3>
        <ul className="mt-6 space-y-3">
          {demoContent.aside.items.map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-sm leading-6 text-[#78756F]">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[#A8A29E]" />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-8 text-xs text-[#A8A29E]">{demoContent.aside.time}</p>
      </aside>
    </section>
  );
};

export default DemoFormSection;


