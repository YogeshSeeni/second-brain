"use client";

import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  dispatchDraft,
  listInbox,
  type InboxDraft,
} from "@/lib/api";

type Filter = "pending" | "all";

function kindTone(kind: string): "ok" | "warn" | "info" | "default" {
  if (kind === "email" || kind === "slack" || kind === "dm") return "info";
  if (kind.startsWith("gh")) return "warn";
  if (kind === "gcal-invite") return "ok";
  return "default";
}

export function InboxClient() {
  const [drafts, setDrafts] = useState<InboxDraft[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("pending");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());

  async function load() {
    try {
      const rows = await listInbox();
      setDrafts(rows);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  async function handleDispatch(path: string) {
    setBusy((s) => new Set(s).add(path));
    try {
      await dispatchDraft(path);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy((s) => {
        const next = new Set(s);
        next.delete(path);
        return next;
      });
    }
  }

  function toggle(path: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const rows =
    drafts?.filter((d) => (filter === "pending" ? !d.dispatched : true)) ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl space-y-4">
        <Card>
          <CardHeader
            title="inbox"
            subtitle="drafts the agent wrote — you send them"
            right={
              <div className="flex items-center gap-1 text-[10px] uppercase tracking-widest">
                <button
                  type="button"
                  onClick={() => setFilter("pending")}
                  className={`rounded px-2 py-0.5 ${
                    filter === "pending"
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  pending
                </button>
                <button
                  type="button"
                  onClick={() => setFilter("all")}
                  className={`rounded px-2 py-0.5 ${
                    filter === "all"
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  all
                </button>
              </div>
            }
          />
          <CardBody>
            {err && !drafts && (
              <div className="font-mono text-[11px] text-red-400">{err}</div>
            )}
            {drafts && rows.length === 0 && (
              <p className="text-xs text-zinc-600">
                {filter === "pending"
                  ? "no pending drafts"
                  : "inbox is empty"}
              </p>
            )}
            <ul className="space-y-2">
              {rows.map((d) => (
                <li
                  key={d.path}
                  className="rounded border border-zinc-800 bg-zinc-950/60"
                >
                  <div className="flex items-start gap-2 px-3 py-2">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <Badge tone={kindTone(d.kind)}>{d.kind}</Badge>
                        {d.dispatched && <Badge tone="ok">sent</Badge>}
                        <span className="truncate text-sm text-zinc-200">
                          {d.title}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-zinc-500">
                        {d.to && <span>to: {d.to}</span>}
                        {d.subject && <span>re: {d.subject}</span>}
                        {d.drafted_at && <span>drafted {d.drafted_at}</span>}
                        {d.expires && (
                          <span className="text-amber-400">
                            expires {d.expires}
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-[10px] text-zinc-600">
                        {d.path}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <button
                        type="button"
                        onClick={() => toggle(d.path)}
                        className="rounded border border-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-widest text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
                      >
                        {expanded.has(d.path) ? "hide" : "view"}
                      </button>
                      {!d.dispatched && (
                        <button
                          type="button"
                          onClick={() => handleDispatch(d.path)}
                          disabled={busy.has(d.path)}
                          className="rounded border border-green-900/60 bg-green-950/40 px-2 py-0.5 text-[10px] uppercase tracking-widest text-green-300 hover:border-green-700 hover:text-green-100 disabled:opacity-40"
                        >
                          {busy.has(d.path) ? "…" : "mark sent"}
                        </button>
                      )}
                    </div>
                  </div>
                  {expanded.has(d.path) && (
                    <pre className="whitespace-pre-wrap break-words border-t border-zinc-900 px-3 py-2 font-mono text-[11px] text-zinc-400">
                      {d.body || "_(empty body)_"}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
