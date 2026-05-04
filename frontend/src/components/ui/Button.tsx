// src/components/ui/Button.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "outline";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  fullWidth?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "border border-transparent bg-[var(--accent-primary)] text-white shadow-sm ring-1 ring-black/5 hover:bg-[var(--accent-hover)] hover:shadow-md active:bg-[var(--accent-hover)]",
  secondary:
    "border border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm hover:border-[var(--border-strong,var(--border))] hover:bg-[var(--bg-card-hover,var(--bg-card))]",
  ghost:
    "border border-transparent bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
  danger:
    "border border-transparent bg-[var(--danger,var(--accent-primary))] text-white shadow-sm ring-1 ring-black/5 hover:brightness-95 active:brightness-90",
  outline:
    "border border-[color:color-mix(in_srgb,var(--accent-primary)_28%,transparent)] bg-transparent text-[var(--accent-primary)] hover:bg-[var(--accent-muted)]",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "min-h-8 px-3 py-1.5 text-[12px] rounded-lg gap-1.5",
  md: "min-h-10 px-4 py-2 text-[13px] rounded-xl gap-2",
  lg: "min-h-11 px-5 py-2.5 text-[14px] rounded-xl gap-2",
};

const iconSizeClasses: Record<ButtonSize, string> = {
  sm: "[&_svg]:h-3.5 [&_svg]:w-3.5",
  md: "[&_svg]:h-4 [&_svg]:w-4",
  lg: "[&_svg]:h-4 [&_svg]:w-4",
};

const spinnerSizeClasses: Record<ButtonSize, string> = {
  sm: "h-3.5 w-3.5 border-[1.5px]",
  md: "h-4 w-4 border-2",
  lg: "h-4 w-4 border-2",
};

const loadingTextSizeClasses: Record<ButtonSize, string> = {
  sm: "text-[12px]",
  md: "text-[13px]",
  lg: "text-[14px]",
};

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      type = "button",
      variant = "primary",
      size = "md",
      isLoading = false,
      disabled = false,
      fullWidth = false,
      className,
      children,
      leftIcon,
      rightIcon,
      ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || isLoading;
    const isSolid = variant === "primary" || variant === "danger";

    const spinnerClass = isSolid
      ? "border-white/70 border-t-transparent"
      : "border-[var(--accent-primary)]/50 border-t-transparent";

    const loadingTextClass = isSolid
      ? "text-white/90"
      : "text-[var(--text-secondary)]";

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-busy={isLoading || undefined}
        className={cn(
          "relative inline-flex shrink-0 items-center justify-center whitespace-nowrap font-semibold tracking-[-0.01em]",
          "transition-[background-color,border-color,color,box-shadow,transform] duration-150",
          "active:scale-[0.99]",
          "disabled:pointer-events-none disabled:opacity-50",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
          variantClasses[variant],
          sizeClasses[size],
          iconSizeClasses[size],
          fullWidth && "w-full",
          className,
        )}
        {...props}
      >
        {isLoading ? (
          <span className="inline-flex items-center gap-2">
            <span
              aria-hidden="true"
              className={cn(
                "animate-spin rounded-full",
                spinnerSizeClasses[size],
                spinnerClass,
              )}
            />
            <span
              className={cn(
                "font-semibold tracking-[-0.01em]",
                loadingTextSizeClasses[size],
                loadingTextClass,
              )}
            >
              Загрузка…
            </span>
          </span>
        ) : (
          <span className="inline-flex items-center justify-center gap-2">
            {leftIcon ? (
              <span aria-hidden="true" className="inline-flex items-center">
                {leftIcon}
              </span>
            ) : null}

            <span>{children}</span>

            {rightIcon ? (
              <span aria-hidden="true" className="inline-flex items-center">
                {rightIcon}
              </span>
            ) : null}
          </span>
        )}
      </button>
    );
  },
);

Button.displayName = "Button";

export default Button;

