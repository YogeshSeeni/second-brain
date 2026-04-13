"use client";

import { useEffect, useState } from "react";
import { ackNudge, getDashboard, type DashboardResponse } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtRelative(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function recoveryTone(score: number | null): "ok" | "warn" | "error" | "default" {
  if (score === null) return "default";
  if (score >= 67) return "ok";
  if (score >= 34) return "warn";
  return "error";
}

export function DashboardClient() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ackingIds, setAckingIds] = useState<Set<number>>(new Set());

  async function handleAck(id: number) {
    setAckingIds((s) => new Set(s).add(id));
    setData((d) =>
      d ? { ...d, nudges: d.nudges.filter((n) => n.id !== id) } : d,
    );
    try {
      await ackNudge(id);
    } catch (e) {
      setErr((e as Error).message);
      try {
        const fresh = await getDashboard();
        setData(fresh);
      } catch {}
    } finally {
      setAckingIds((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
    }
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await getDashboard();
        if (active) {
          setData(res);
          setErr(null);
        }
      } catch (e) {
        if (active) setErr((e as Error).message);
      }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  if (err && !data) {
    return (
      <div className="p-6">
        <Card>
          <CardBody>
            <div className="text-xs text-zinc-500">
              dashboard endpoint not available yet
            </div>
            <div className="mt-1 font-mono text-[11px] text-zinc-600">{err}</div>
          </CardBody>
        </Card>
      </div>
    );
  }

  const recovery = data?.recovery ?? null;
  const calendar = data?.calendar ?? [];
  const priorities = data?.priorities ?? [];
  const activity = data?.recent_activity ?? [];
  const nudges = data?.nudges ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="recovery"
            subtitle="whoop v2"
            right={
              <Badge tone={recoveryTone(recovery?.score ?? null)}>
                {recovery?.score != null ? `${recovery.score}%` : "—"}
              </Badge>
            }
          />
          <CardBody>
            {recovery ? (
              <dl className="grid grid-cols-2 gap-2 text-xs text-zinc-400">
                <div>
                  <dt className="text-zinc-600">hrv</dt>
                  <dd className="text-zinc-200">
                    {recovery.hrv_ms != null ? `${recovery.hrv_ms.toFixed(0)}ms` : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-zinc-600">resting hr</dt>
                  <dd className="text-zinc-200">{recovery.resting_hr ?? "—"}</dd>
                </div>
              </dl>
            ) : (
              <p className="text-xs text-zinc-600">no whoop data yet</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="today" subtitle="calendar" />
          <CardBody>
            {calendar.length === 0 ? (
              <p className="text-xs text-zinc-600">no events</p>
            ) : (
              <ul className="space-y-1.5">
                {calendar.slice(0, 5).map((ev) => (
                  <li key={ev.id} className="flex items-baseline gap-2 text-xs">
                    <span className="shrink-0 text-zinc-500">{fmtTime(ev.start_at)}</span>
                    <span className="truncate text-zinc-200">{ev.summary}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="priorities" subtitle="from morning note" />
          <CardBody>
            {priorities.length === 0 ? (
              <p className="text-xs text-zinc-600">no morning note yet</p>
            ) : (
              <ol className="list-inside list-decimal space-y-1 text-sm text-zinc-200 marker:text-zinc-600">
                {priorities.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="recent activity" subtitle="agent · jobs · ticks" />
          <CardBody>
            {activity.length === 0 ? (
              <p className="text-xs text-zinc-600">no activity</p>
            ) : (
              <ul className="space-y-1.5">
                {activity.map((a, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <Badge tone={a.state === "error" ? "error" : "default"}>
                      {a.kind}
                    </Badge>
                    <span className="flex-1 truncate text-zinc-300">{a.label}</span>
                    <span className="shrink-0 text-zinc-600">{fmtRelative(a.at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="nudges" subtitle="agent surfaced" />
          <CardBody>
            {nudges.length === 0 ? (
              <p className="text-xs text-zinc-600">nothing to surface</p>
            ) : (
              <ul className="space-y-2">
                {nudges.map((n) => (
                  <li
                    key={n.id}
                    className="flex items-start gap-2 text-xs text-zinc-300"
                  >
                    <div className="flex-1">
                      <div className="text-[10px] uppercase tracking-widest text-zinc-600">
                        {n.kind}
                      </div>
                      {n.body}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAck(n.id)}
                      disabled={ackingIds.has(n.id)}
                      className="shrink-0 rounded border border-zinc-700 px-2 py-0.5 text-[10px] uppercase tracking-widest text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200 disabled:opacity-40"
                    >
                      ack
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
