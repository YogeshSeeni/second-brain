import type { ButtonHTMLAttributes } from "react";

type Variant = "default" | "ghost" | "outline" | "danger";
type Size = "sm" | "md";

const variantClass: Record<Variant, string> = {
  default:
    "bg-zinc-100 text-zinc-900 hover:bg-white disabled:bg-zinc-500 disabled:text-zinc-300",
  ghost:
    "bg-transparent text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 disabled:text-zinc-600",
  outline:
    "border border-zinc-800 bg-transparent text-zinc-200 hover:border-zinc-600 hover:text-white disabled:text-zinc-600",
  danger:
    "bg-red-900/60 text-red-100 hover:bg-red-900 disabled:bg-zinc-800 disabled:text-zinc-500",
};

const sizeClass: Record<Size, string> = {
  sm: "h-7 px-2 text-xs",
  md: "h-9 px-3 text-sm",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

export function Button({
  className = "",
  variant = "default",
  size = "md",
  type = "button",
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded font-medium transition-colors disabled:cursor-not-allowed ${variantClass[variant]} ${sizeClass[size]} ${className}`}
      {...rest}
    />
  );
}
