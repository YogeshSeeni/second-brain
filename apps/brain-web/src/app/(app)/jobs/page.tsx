"use client";

import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { listJobs, runJob, type JobRun, type JobSummary } from "@/lib/api";

function fmtRelative(ts: number | null | undefined): string {
  if (!ts) return "never";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmtDuration(run: JobRun | null): string {
  if (!run || !run.ended_at) return "—";
  const s = run.ended_at - run.started_at;
  if (s < 60) return `${s.toFixed(0)}s`;
  return `${(s / 60).toFixed(1)}m`;
}

function stateTone(state: string | undefined): "ok" | "warn" | "error" | "default" {
  if (state === "done") return "ok";
  if (state === "running") return "warn";
  if (state === "error") return "error";
  return "default";
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState<Set<string>>(new Set());

  async function load() {
    try {
      setJobs(await listJobs());
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  async function handleRun(name: string) {
    setRunning((s) => new Set(s).add(name));
    try {
      await runJob(name);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRunning((s) => {
        const next = new Set(s);
        next.delete(name);
        return next;
      });
    }
  }

  if (err && !jobs) {
    return (
      <div className="p-6">
        <Card>
          <CardBody>
            <div className="text-xs text-zinc-500">jobs endpoint not available</div>
            <div className="mt-1 font-mono text-[11px] text-zinc-600">{err}</div>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <Card>
          <CardHeader title="jobs" subtitle="named tasks · manual + scheduled" />
          <CardBody className="p-0">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-widest text-zinc-600">
                  <th className="border-b border-zinc-900 px-4 py-2 font-medium">name</th>
                  <th className="border-b border-zinc-900 px-4 py-2 font-medium">schedule</th>
                  <th className="border-b border-zinc-900 px-4 py-2 font-medium">last run</th>
                  <th className="border-b border-zinc-900 px-4 py-2 font-medium">duration</th>
                  <th className="border-b border-zinc-900 px-4 py-2 font-medium">state</th>
                  <th className="border-b border-zinc-900 px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {jobs?.map((j) => (
                  <tr key={j.name} className="text-zinc-300">
                    <td className="border-b border-zinc-900 px-4 py-2 font-mono text-xs">
                      {j.name}
                    </td>
                    <td className="border-b border-zinc-900 px-4 py-2 text-xs text-zinc-500">
                      {j.schedule ?? "ad-hoc"}
                    </td>
                    <td className="border-b border-zinc-900 px-4 py-2 text-xs text-zinc-500">
                      {fmtRelative(j.last_run?.started_at)}
                    </td>
                    <td className="border-b border-zinc-900 px-4 py-2 text-xs text-zinc-500">
                      {fmtDuration(j.last_run)}
                    </td>
                    <td className="border-b border-zinc-900 px-4 py-2">
                      <Badge tone={stateTone(j.last_run?.state)}>
                        {j.last_run?.state ?? "—"}
                      </Badge>
                    </td>
                    <td className="border-b border-zinc-900 px-4 py-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRun(j.name)}
                        disabled={running.has(j.name)}
                      >
                        {running.has(j.name) ? "running…" : "run now"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs && jobs.length === 0 && (
              <div className="px-4 py-3 text-xs text-zinc-600">no jobs registered</div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
