// src/components/ui/Field.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

interface FieldProps {
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
  labelClassName?: string;
  contentClassName?: string;
  hintClassName?: string;
  htmlFor?: string;
  hideLabel?: boolean;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const Field: React.FC<FieldProps> = ({
  label,
  required = false,
  hint,
  error,
  children,
  className,
  labelClassName,
  contentClassName,
  hintClassName,
  htmlFor,
  hideLabel = false,
}) => {
  const reactId = React.useId();
  const generatedControlId = `field-${reactId.replace(/[:]/g, "")}`;

  const controlId = htmlFor || generatedControlId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;

  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  const child = React.Children.only(children);

  const enhancedChild = React.isValidElement(child)
    ? React.cloneElement(
        child as React.ReactElement<{
          id?: string;
          "aria-describedby"?: string;
          "aria-invalid"?: boolean;
          required?: boolean;
        }>,
        {
          id: (child.props as { id?: string }).id ?? controlId,
          "aria-describedby":
            (child.props as { "aria-describedby"?: string })["aria-describedby"] ??
            describedBy,
          "aria-invalid":
            (child.props as { "aria-invalid"?: boolean })["aria-invalid"] ??
            (error ? true : undefined),
          required:
            (child.props as { required?: boolean }).required ?? required,
        },
      )
    : child;

  return (
    <div className={cn("space-y-1.5", className)}>
      <label
        htmlFor={controlId}
        className={cn(
          hideLabel
            ? "sr-only"
            : "block text-xs font-medium text-[var(--text-secondary)]",
          labelClassName,
        )}
      >
        <span>{label}</span>
        {required && (
          <span
            className="ml-1 text-[var(--color-error-text)]"
            aria-hidden="true"
          >
            *
          </span>
        )}
      </label>

      <div className={contentClassName}>{enhancedChild}</div>

      {error ? (
        <p
          id={errorId}
          className={cn(
            "text-[11px] leading-5 text-[var(--color-error-text)]",
            hintClassName,
          )}
        >
          {error}
        </p>
      ) : hint ? (
        <p
          id={hintId}
          className={cn(
            "text-[11px] leading-5 text-[var(--text-faint)]",
            hintClassName,
          )}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
};

export default Field;


