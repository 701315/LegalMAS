export const marketingTheme = {
  container: {
    hero: "mx-auto w-full max-w-[1480px] px-4 sm:px-6 lg:px-10 xl:px-12",
    section: "mx-auto w-full max-w-[1360px] px-4 sm:px-6 lg:px-8 xl:px-10",
    prose: "mx-auto w-full max-w-[880px] px-4 sm:px-6 lg:px-8",
  },

  section: {
    base: "py-20 lg:py-28",
    compact: "py-14 lg:py-18",
    relaxed: "py-24 lg:py-32",
  },

  surface: {
    subtle: "bg-white/[0.025] border border-white/10",
    soft: "bg-white/[0.03] border border-white/10",
    strong: "bg-white/[0.04] border border-white/10",
    elevated: "bg-white/[0.05] border border-white/10 shadow-2xl shadow-black/30",
  },

  radius: {
    sm: "rounded-xl",
    md: "rounded-2xl",
    lg: "rounded-[28px]",
    xl: "rounded-[32px]",
    hero: "rounded-[36px]",
    pill: "rounded-full",
  },

  text: {
    eyebrow: "text-xs uppercase tracking-[0.18em] text-slate-500",
    title: "text-3xl font-semibold tracking-tight text-white lg:text-5xl",
    subtitle: "mt-4 text-base leading-relaxed text-slate-400 lg:text-lg",
    body: "text-sm leading-relaxed text-slate-400",
    bodyLg: "text-base leading-relaxed text-slate-300",
    cardTitle: "text-xl font-semibold text-white",
    cardTitleLg: "text-2xl font-semibold text-white lg:text-3xl",
  },

  grid: {
    two: "grid gap-6 md:grid-cols-2",
    three: "grid gap-6 md:grid-cols-3",
    four: "grid gap-4 sm:grid-cols-2 xl:grid-cols-4",
  },

  button: {
    primary:
      "inline-flex items-center justify-center rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-slate-200",
    secondary:
      "inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/[0.08]",
    tertiary:
      "inline-flex items-center gap-2 text-sm font-medium text-white transition-colors hover:text-slate-300",
  },

  badge: {
    base: "inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300",
    success:
      "inline-flex items-center rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-200",
  },

  input: {
    base: "w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3.5 text-sm text-white outline-none transition-colors placeholder:text-slate-500 focus:border-white/25 focus:bg-white/[0.05]",
    label: "mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500",
  },

  divider: "border-white/10",
} as const;
