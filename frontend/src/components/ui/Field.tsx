// src/components/ui/Field.tsx

import React, { useId } from "react";

interface FieldProps {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, required = false, hint, children }) => {
  const hintId = useId();

  return (
    <div>
      <label className="mb-1 block text-xs text-gray-600">
        {label}
        {required && <span className="text-red-500">*</span>}
      </label>

      {children}

      {hint && (
        <p id={hintId} className="mt-1 text-[11px] text-gray-400">
          {hint}
        </p>
      )}
    </div>
  );
};

export default Field;


