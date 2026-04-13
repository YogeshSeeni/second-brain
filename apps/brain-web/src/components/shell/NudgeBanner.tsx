"use client";

import { useEffect, useState } from "react";
import { ackNudge, BRAIN_CORE_URL } from "@/lib/api";

type Nudge = {
  id: number;
  kind: string;
  body: string;
  created_at: number;
};

const POLL_MS = 30_000;

async function fetchTop(): Promise<Nudge[]> {
  const res = await fetch(`${BRAIN_CORE_URL}/api/nudges?limit=5`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`nudges ${res.status}`);
  return (await res.json()) as Nudge[];
}

export function NudgeBanner() {
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [acking, setAcking] = useState<Set<number>>(new Set());
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const rows = await fetchTop();
        if (alive) setNudges(rows);
      } catch {
        // soft-fail — banner just disappears if brain-core is unreachable
      }
    }
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  async function handleAck(id: number) {
    setAcking((s) => new Set(s).add(id));
    setNudges((rows) => rows.filter((n) => n.id !== id));
    try {
      await ackNudge(id);
    } finally {
      setAcking((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
    }
  }

  if (nudges.length === 0) return null;

  const top = nudges[0];
  const rest = nudges.length - 1;

  return (
    <div className="shrink-0 border-b border-amber-900/40 bg-amber-950/30 px-4 py-1.5 text-xs text-amber-200">
      <div className="flex items-center gap-2">
        <span className="rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-amber-200">
          {top.kind}
        </span>
        <span className="flex-1 truncate">{top.body}</span>
        {rest > 0 && (
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="shrink-0 rounded border border-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-300 hover:border-amber-600 hover:text-amber-100"
          >
            {collapsed ? `show ${rest} more` : "hide"}
          </button>
        )}
        <button
          type="button"
          onClick={() => handleAck(top.id)}
          disabled={acking.has(top.id)}
          className="shrink-0 rounded border border-amber-900/60 px-2 py-0.5 text-[10px] uppercase tracking-widest text-amber-300 hover:border-amber-600 hover:text-amber-100 disabled:opacity-40"
        >
          ack
        </button>
      </div>
      {!collapsed && rest > 0 && (
        <ul className="mt-1 space-y-1 pl-2">
          {nudges.slice(1).map((n) => (
            <li key={n.id} className="flex items-center gap-2">
              <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-amber-300">
                {n.kind}
              </span>
              <span className="flex-1 truncate">{n.body}</span>
              <button
                type="button"
                onClick={() => handleAck(n.id)}
                disabled={acking.has(n.id)}
                className="shrink-0 rounded border border-amber-900/60 px-2 py-0.5 text-[10px] uppercase tracking-widest text-amber-300 hover:border-amber-600 hover:text-amber-100 disabled:opacity-40"
              >
                ack
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
