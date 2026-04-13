"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

export function StatusFooter() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;
    async function check() {
      try {
        const res = await getHealth();
        if (active) {
          setOnline(res.ok);
          setCheckedAt(new Date());
        }
      } catch {
        if (active) {
          setOnline(false);
          setCheckedAt(new Date());
        }
      }
    }
    check();
    const id = setInterval(check, 30_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const dot =
    online === null
      ? "bg-zinc-600"
      : online
        ? "bg-emerald-500"
        : "bg-red-500";

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-zinc-900 bg-zinc-950/90 px-4 text-[11px] text-zinc-500">
      <div className="flex items-center gap-1.5">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
        <span>
          core {online === null ? "checking" : online ? "online" : "offline"}
        </span>
      </div>
      <div className="h-3 w-px bg-zinc-800" />
      <div>agent idle</div>
      <div className="h-3 w-px bg-zinc-800" />
      <div>
        {checkedAt
          ? `last check ${checkedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
          : "—"}
      </div>
    </footer>
  );
}
