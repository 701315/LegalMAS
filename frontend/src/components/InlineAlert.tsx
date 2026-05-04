// =============================================================
// src/components/InlineAlert.tsx
// Унифицированный inline-alert для product UI.
// =============================================================

import React from "react";

type InlineAlertTone = "success" | "error" | "info" | "warning";

interface InlineAlertProps {
  tone: InlineAlertTone;
  message: string | null;
}

const toneClasses: Record<InlineAlertTone, string> = {
  success:
    "border-[rgba(67,122,34,0.18)] bg-[rgba(67,122,34,0.08)] text-[rgb(47,93,24)]",
  error:
    "border-[rgba(161,53,68,0.22)] bg-[rgba(161,53,68,0.08)] text-[rgb(120,35,46)]",
  info:
    "border-[rgba(1,105,111,0.18)] bg-[var(--accent-muted)] text-[var(--accent-primary)]",
  warning:
    "border-[rgba(150,66,25,0.18)] bg-[rgba(150,66,25,0.08)] text-[rgb(122,59,27)]",
};

const InlineAlert: React.FC<InlineAlertProps> = ({ tone, message }) => {
  return (
    <div
      aria-live={tone === "error" ? "assertive" : "polite"}
      aria-atomic="true"
      className="min-h-[44px]"
    >
      {message ? (
        <div
          role={tone === "error" ? "alert" : "status"}
          className={[
            "rounded-[18px] border px-4 py-3 text-sm shadow-sm",
            toneClasses[tone],
          ].join(" ")}
        >
          {message}
        </div>
      ) : (
        <div className="sr-only" role="status" />
      )}
    </div>
  );
};

export default InlineAlert;




