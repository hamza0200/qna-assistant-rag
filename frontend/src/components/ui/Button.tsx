import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-action text-white hover:bg-action-hover disabled:bg-action/50",
  secondary: "border border-line bg-surface text-ink hover:border-muted disabled:text-muted",
  ghost: "text-muted hover:bg-line/50 hover:text-ink disabled:opacity-50",
  danger: "border border-bad/30 bg-surface text-bad hover:bg-bad hover:text-white",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", type = "button", ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
