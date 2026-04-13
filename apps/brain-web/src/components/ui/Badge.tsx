import type { HTMLAttributes } from "react";

type Tone = "default" | "ok" | "warn" | "error" | "info";

const toneClass: Record<Tone, string> = {
  default: "bg-zinc-900 text-zinc-300 border-zinc-800",
  ok: "bg-emerald-950/60 text-emerald-300 border-emerald-900/60",
  warn: "bg-amber-950/60 text-amber-300 border-amber-900/60",
  error: "bg-red-950/60 text-red-300 border-red-900/60",
  info: "bg-sky-950/60 text-sky-300 border-sky-900/60",
};

type Props = HTMLAttributes<HTMLSpanElement> & { tone?: Tone };

export function Badge({ className = "", tone = "default", ...rest }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${toneClass[tone]} ${className}`}
      {...rest}
    />
  );
}
