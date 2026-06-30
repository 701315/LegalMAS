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

  const inputClass =
    "w-full rounded-[14px] border border-[#E5E2DA] bg-white px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 outline-none transition-colors focus:border-stone-400";

  return (
    <section className="mt-12 grid gap-6 lg:grid-cols-[1fr_0.75fr] lg:items-start">

      {/* Форма */}
      <div className="rounded-[28px] border border-[#E5E2DA] bg-white p-7 lg:p-9">
        <h2 className="font-serif text-2xl tracking-[-0.03em] text-stone-950">
          {demoContent.form.title}
        </h2>
        <p className="mt-3 text-sm leading-7 text-stone-600">{demoContent.form.subtitle}</p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              {demoContent.form.fields.name}
            </label>
            <input type="text" required value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={demoContent.form.placeholders.name}
              className={inputClass} />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              {demoContent.form.fields.company}
            </label>
            <input type="text" value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={demoContent.form.placeholders.company}
              className={inputClass} />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              {demoContent.form.fields.email}
            </label>
            <input type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={demoContent.form.placeholders.email}
              className={inputClass} />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              {demoContent.form.fields.useCase}
            </label>
            <textarea required rows={5} value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              placeholder={demoContent.form.placeholders.useCase}
              className={`${inputClass} resize-none`} />
          </div>
          <p className="text-xs text-stone-400">{demoContent.form.note}</p>
          <button type="submit"
            className="inline-flex items-center gap-2 rounded-full bg-[#111827] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1f2937]">
            {demoContent.form.submit}
          </button>
        </form>
      </div>

      {/* Aside */}
      <aside className="rounded-[28px] border border-[#E5E2DA] bg-[#F1EFEA] p-7">
        <h3 className="font-serif text-xl tracking-[-0.02em] text-stone-950">
          {demoContent.aside.title}
        </h3>
        <ul className="mt-6 space-y-3">
          {demoContent.aside.items.map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-sm leading-6 text-stone-600">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-stone-400" />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-8 text-xs text-stone-400">{demoContent.aside.time}</p>
      </aside>
    </section>
  );
};

export default DemoFormSection;

