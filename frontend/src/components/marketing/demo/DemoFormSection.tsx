import React, { useState } from "react";
import { demoContent } from "../../../content/demoContent";

const DemoFormSection: React.FC = () => {
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [useCase, setUseCase] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const subject = encodeURIComponent("Запрос демо LegalMAS");
    const body = encodeURIComponent(
      `Имя: ${name}\nКомпания: ${company}\nEmail: ${email}\n\nСценарий:\n${useCase}`
    );

    window.location.href =
      `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <section className="mt-16 grid lg:grid-cols-[1fr_0.8fr] gap-8 items-start">
      <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 lg:p-10">
        <h2 className="text-2xl font-semibold">{demoContent.form.title}</h2>
        <p className="mt-4 text-sm text-slate-400 leading-relaxed max-w-2xl">
          {demoContent.form.subtitle}
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">
              {demoContent.form.fields.name}
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={demoContent.form.placeholders.name}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-white/30"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1.5">
              {demoContent.form.fields.company}
            </label>
            <input
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={demoContent.form.placeholders.company}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-white/30"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1.5">
              {demoContent.form.fields.email}
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={demoContent.form.placeholders.email}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-white/30"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1.5">
              {demoContent.form.fields.useCase}
            </label>
            <textarea
              required
              rows={6}
              value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              placeholder={demoContent.form.placeholders.useCase}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-white/30 resize-none"
            />
          </div>

          <div className="text-xs text-slate-500">{demoContent.form.note}</div>

          <button
            type="submit"
            className="inline-flex items-center justify-center rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-slate-200 transition-colors"
          >
            {demoContent.form.submit}
          </button>
        </form>
      </div>

      <aside className="rounded-3xl border border-white/10 bg-white/[0.03] p-8">
        <h3 className="text-xl font-semibold">{demoContent.aside.title}</h3>
        <ul className="mt-6 space-y-4 text-sm text-slate-400">
          {demoContent.aside.items.map((item) => (
            <li key={item}>- {item}</li>
          ))}
        </ul>
        <div className="mt-8 text-sm text-slate-500">{demoContent.aside.time}</div>
      </aside>
    </section>
  );
};

export default DemoFormSection;

