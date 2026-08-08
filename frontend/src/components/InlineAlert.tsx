// src/components/InlineAlert.tsx

import React from "react";
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Info,
} from "lucide-react";

type InlineAlertTone = "success" | "error" | "info" | "warning";

interface InlineAlertProps {
  tone: InlineAlertTone;
  message: string | null;
}

interface ToneConfig {
  containerClass: string;
  icon: React.ReactNode;
}

const TONE_CONFIG: Record<InlineAlertTone, ToneConfig> = {
  success: {
    containerClass:
      "border-[var(--color-success-border)] " +
      "bg-[var(--color-success-bg)] " +
      "text-[var(--color-success-text)]",
    icon: <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />,
  },
  error: {
    containerClass:
      "border-[var(--color-error-border)] " +
      "bg-[var(--color-error-bg)] " +
      "text-[var(--color-error-text)]",
    icon: <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />,
  },
  warning: {
    containerClass:
      "border-[var(--color-warning-border)] " +
      "bg-[var(--color-warning-bg)] " +
      "text-[var(--color-warning-text)]",
    icon: <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />,
  },
  info: {
    containerClass:
      "border-[color:color-mix(in_oklab,var(--accent-primary)_20%,transparent)] " +
      "bg-[var(--accent-muted)] " +
      "text-[var(--accent-primary)]",
    icon: <Info className="h-4 w-4 shrink-0" aria-hidden="true" />,
  },
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
            "flex items-start gap-3 rounded-[var(--radius-lg)] border px-4 py-3 text-sm shadow-sm",
            TONE_CONFIG[tone].containerClass,
          ].join(" ")}
        >
          <span className="mt-0.5">{TONE_CONFIG[tone].icon}</span>
          <span className="leading-relaxed">{message}</span>
        </div>
      ) : (
        <div className="sr-only" role="status" />
      )}
    </div>
  );
};

export default InlineAlert;


