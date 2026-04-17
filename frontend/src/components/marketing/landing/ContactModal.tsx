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
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 backdrop-blur-md"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative w-full max-w-5xl overflow-hidden rounded-[32px] border border-white/10 bg-slate-950 shadow-2xl shadow-black/50">
        <button
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute right-4 top-4 z-10 inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-300 transition-colors hover:bg-white/[0.08] hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
          <div className="border-b border-white/10 bg-white/[0.03] p-8 lg:border-b-0 lg:border-r lg:p-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300">
              <Shield className="h-3.5 w-3.5 text-emerald-300" />
              Enterprise demo request
            </div>

            <h3 className="mt-6 max-w-md text-3xl font-semibold tracking-tight text-white">
              {landingContent.finalCta.title}
            </h3>

            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400 lg:text-base">
              Расскажи о типах документов, playbooks и текущем процессе review — так демо можно сделать
              предметным, а не общим.
            </p>

            <div className="mt-8 space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">01</div>
                <p className="mt-2 text-sm text-slate-300">
                  Обсудим сценарий: M&A, DD, contract review или внутренний аудит.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">02</div>
                <p className="mt-2 text-sm text-slate-300">
                  Покажем document flow: загрузка, checks, source-linked results и export.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">03</div>
                <p className="mt-2 text-sm text-slate-300">
                  При необходимости отдельно разберём security model, local-first режим и архитектуру.
                </p>
              </div>
            </div>
          </div>

          <div className="p-8 lg:p-10">
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-2 text-sm text-slate-400">
                <Mail className="h-4 w-4" />
                Ответ придёт на указанный рабочий email
              </div>

              <form onSubmit={onSubmit} className="mt-8 space-y-5">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">
                    Рабочий email
                  </label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    placeholder="name@company.com"
                    className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3.5 text-sm text-white outline-none transition-colors placeholder:text-slate-500 focus:border-white/25 focus:bg-white/[0.05]"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">
                    Сценарий, типы документов, объём
                  </label>
                  <textarea
                    required
                    rows={7}
                    value={message}
                    onChange={(e) => onMessageChange(e.target.value)}
                    placeholder="Например: DD для пакета SPA / SHA / NDA, 300+ документов, нужен source-linked результат и экспорт в Excel."
                    className="w-full resize-none rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3.5 text-sm text-white outline-none transition-colors placeholder:text-slate-500 focus:border-white/25 focus:bg-white/[0.05]"
                  />
                </div>

                <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/10 px-4 py-3 text-xs leading-relaxed text-emerald-100/90">
                  Если у тебя чувствительный сценарий, можно сразу указать требования к local-first
                  обработке, ограничения по cloud LLM и ожидания по security review.
                </div>

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <button
                    type="submit"
                    className="inline-flex items-center justify-center rounded-2xl bg-white px-5 py-3.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-slate-200"
                  >
                    Отправить запрос
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={onClose}
                    className="inline-flex items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.08]"
                  >
                    Отмена
                  </button>
                </div>

                <p className="text-xs leading-relaxed text-slate-500">
                  Сейчас форма открывает почтовый клиент через mailto. Позже её можно перевести на backend
                  endpoint или CRM flow без изменения UI-структуры.
                </p>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContactModal;

