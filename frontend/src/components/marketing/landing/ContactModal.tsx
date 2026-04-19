import React from "react";
import { ArrowRight, Mail, Shield, X } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

interface ContactModalProps {
  open: boolean;
  email: string;
  message: string;
  onEmailChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

const ContactModal: React.FC<ContactModalProps> = ({
  open,
  email,
  message,
  onEmailChange,
  onMessageChange,
  onClose,
  onSubmit,
}) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[rgba(32,27,22,0.48)] px-4 backdrop-blur-md"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative w-full max-w-6xl overflow-hidden rounded-[36px] border border-stone-900/10 bg-[#f7f3ea] shadow-[0_32px_120px_rgba(28,25,23,0.18)]">
        <button
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute right-4 top-4 z-10 inline-flex h-10 w-10 items-center justify-center rounded-full border border-stone-900/10 bg-white/80 text-stone-700 transition-colors hover:bg-white hover:text-stone-950"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="grid lg:grid-cols-[0.95fr_1.05fr]">
          <div className="border-b border-stone-900/10 bg-[#ece5d8] p-8 lg:border-b-0 lg:border-r lg:p-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-stone-900/10 bg-white/70 px-3 py-1.5 text-xs text-stone-700">
              <Shield className="h-3.5 w-3.5" />
              Enterprise demo request
            </div>

            <h3 className="mt-6 max-w-md font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950">
              {landingContent.finalCta.title}
            </h3>

            <p className="mt-4 max-w-md text-sm leading-7 text-stone-700 lg:text-base">
              Расскажи о типах документов, playbooks и текущем процессе review — так демо можно сделать предметным, а не общим.
            </p>

            <div className="mt-8 rounded-[28px] border border-stone-900/10 bg-white/75 p-5">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                Demo path
              </div>
              <div className="mt-4 space-y-3">
                {[
                  "Обсудим сценарий: M&A, DD, contract review или внутренний аудит.",
                  "Покажем document flow: загрузка, checks, source-linked results и export.",
                  "При необходимости отдельно разберём security model, local-first режим и архитектуру.",
                ].map((item, index) => (
                  <div key={item} className="rounded-2xl bg-[#f7f3ea] px-4 py-4">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-950 text-xs font-semibold text-[#f7f3ea]">
                        0{index + 1}
                      </div>
                      <p className="text-sm leading-6 text-stone-700">{item}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="p-8 lg:p-10">
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-2 text-sm text-stone-600">
                <Mail className="h-4 w-4" />
                Ответ придёт на указанный рабочий email
              </div>

              <form onSubmit={onSubmit} className="mt-8 space-y-5">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.14em] text-stone-500">
                    Рабочий email
                  </label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    placeholder="name@company.com"
                    className="w-full rounded-[22px] border border-stone-900/10 bg-white/80 px-4 py-3.5 text-sm text-stone-950 outline-none transition-colors placeholder:text-stone-400 focus:border-stone-900/20 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.14em] text-stone-500">
                    Сценарий, типы документов, объём
                  </label>
                  <textarea
                    required
                    rows={7}
                    value={message}
                    onChange={(e) => onMessageChange(e.target.value)}
                    placeholder="Например: DD для пакета SPA / SHA / NDA, 300+ документов, нужен source-linked результат и экспорт в Excel."
                    className="w-full resize-none rounded-[22px] border border-stone-900/10 bg-white/80 px-4 py-3.5 text-sm text-stone-950 outline-none transition-colors placeholder:text-stone-400 focus:border-stone-900/20 focus:bg-white"
                  />
                </div>

                <div className="rounded-[22px] border border-emerald-900/10 bg-emerald-950 px-4 py-3 text-xs leading-relaxed text-emerald-50/90">
                  Если у тебя чувствительный сценарий, можно сразу указать требования к local-first обработке, ограничения по cloud LLM и ожидания по security review.
                </div>

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <button
                    type="submit"
                    className="inline-flex items-center justify-center rounded-full bg-stone-950 px-5 py-3.5 text-sm font-semibold text-[#f7f3ea] transition-colors hover:bg-stone-800"
                  >
                    Отправить запрос
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={onClose}
                    className="inline-flex items-center justify-center rounded-full border border-stone-900/10 bg-white/70 px-5 py-3.5 text-sm font-medium text-stone-800 transition-colors hover:bg-white"
                  >
                    Закрыть
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContactModal;

