// src/components/InlineAlert.tsx

import React from "react";

type InlineAlertTone = "success" | "error" | "info" | "warning";

interface InlineAlertProps {
  tone: InlineAlertTone;
  message: string | null;
}

const toneClasses: Record<InlineAlertTone, string> = {
  success: "border-green-200 bg-green-50 text-green-700",
  error: "border-red-200 bg-red-50 text-red-700",
  info: "border-blue-200 bg-blue-50 text-blue-700",
  warning: "border-yellow-200 bg-yellow-50 text-yellow-800",
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
          className={`rounded border p-3 text-sm ${toneClasses[tone]}`}
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



