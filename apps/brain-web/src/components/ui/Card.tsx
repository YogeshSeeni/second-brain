import type { HTMLAttributes, ReactNode } from "react";

type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className = "", ...rest }: CardProps) {
  return (
    <div
      className={`rounded border border-zinc-800 bg-zinc-950 ${className}`}
      {...rest}
    />
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-900 px-4 py-3">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-zinc-500">
          {title}
        </div>
        {subtitle && <div className="mt-0.5 text-sm text-zinc-200">{subtitle}</div>}
      </div>
      {right}
    </div>
  );
}

export function CardBody({ className = "", ...rest }: CardProps) {
  return <div className={`px-4 py-3 ${className}`} {...rest} />;
}
