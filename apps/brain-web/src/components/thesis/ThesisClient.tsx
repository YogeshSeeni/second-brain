"use client";

import { useEffect, useState } from "react";
import {
  getThesis,
  runJob,
  type ThesisAxis,
  type ThesisResponse,
} from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

const AXIS_ORDER: ThesisAxis["axis"][] = [
  "research",
  "industry",
  "skills",
  "optionality",
];

const AXIS_SUBTITLE: Record<ThesisAxis["axis"], string> = {
  research: "lab · papers · lanes",
  industry: "firms · roles · offers",
  skills: "depth · compounding",
  optionality: "hedges · second bets",
};

function confidenceLabel(conf: number | null, raw: string | null | undefined): string {
  if (conf != null) return `${Math.round(conf * 100)}%`;
  if (raw && raw.toLowerCase() !== "unreviewed") return raw;
  return "unreviewed";
}

function confidenceTone(conf: number | null): "ok" | "warn" | "error" | "default" {
  if (conf == null) return "default";
  if (conf >= 0.66) return "ok";
  if (conf >= 0.4) return "warn";
  return "error";
}

function ConfidenceBar({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <div className="h-1 w-full rounded-full bg-zinc-900">
        <div className="h-full w-0 rounded-full bg-zinc-700" />
      </div>
    );
  }
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const tone =
    value >= 0.66
      ? "bg-emerald-500"
      : value >= 0.4
        ? "bg-amber-500"
        : "bg-rose-500";
  return (
    <div className="h-1 w-full rounded-full bg-zinc-900">
      <div
        className={`h-full rounded-full ${tone}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function AxisCard({
  axis,
  onStressTest,
  stressing,
}: {
  axis: ThesisAxis;
  onStressTest: () => void;
  stressing: boolean;
}) {
  const label = confidenceLabel(axis.confidence, axis.confidence_raw ?? null);
  return (
    <Card>
      <CardHeader
        title={axis.axis}
        subtitle={AXIS_SUBTITLE[axis.axis]}
        right={<Badge tone={confidenceTone(axis.confidence)}>{label}</Badge>}
      />
      <CardBody className="space-y-3">
        <ConfidenceBar value={axis.confidence} />
        {axis.stance ? (
          <p className="text-xs leading-relaxed text-zinc-300">
            {axis.stance.length > 360
              ? `${axis.stance.slice(0, 360)}…`
              : axis.stance}
          </p>
        ) : (
          <p className="text-xs text-zinc-600">no stance yet</p>
        )}
        {axis.open_questions.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-widest text-zinc-600">
              open questions
            </div>
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-[11px] text-zinc-400 marker:text-zinc-700">
              {axis.open_questions.slice(0, 3).map((q, i) => (
                <li key={i} className="line-clamp-2">
                  {q}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex items-center justify-between pt-1 text-[10px] uppercase tracking-widest text-zinc-600">
          <span>updated {axis.updated ?? "—"}</span>
          <button
            type="button"
            onClick={onStressTest}
            disabled={stressing}
            className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200 disabled:opacity-40"
          >
            {stressing ? "running…" : "stress test"}
          </button>
        </div>
      </CardBody>
    </Card>
  );
}

export function ThesisClient() {
  const [data, setData] = useState<ThesisResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [stressing, setStressing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await getThesis();
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

  async function handleStressTest() {
    setStressing(true);
    setStatus(null);
    try {
      const run = await runJob("thesis-review");
      setStatus(`thesis-review queued · run ${run.id}`);
    } catch (e) {
      setStatus(`failed: ${(e as Error).message}`);
    } finally {
      setStressing(false);
    }
  }

  if (err && !data) {
    return (
      <div className="p-6">
        <Card>
          <CardBody>
            <div className="text-xs text-zinc-500">
              thesis endpoint not available yet
            </div>
            <div className="mt-1 font-mono text-[11px] text-zinc-600">{err}</div>
          </CardBody>
        </Card>
      </div>
    );
  }

  const axes = data?.axes ?? [];
  const evidence = data?.evidence ?? [];
  const byName = new Map(axes.map((a) => [a.axis, a]));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h1 className="text-sm uppercase tracking-widest text-zinc-500">
              leverage thesis
            </h1>
            <p className="text-xs text-zinc-600">
              four axes · stress-tested Sundays by{" "}
              <code className="text-zinc-500">jobs/thesis-review</code>
            </p>
          </div>
          {status && (
            <div className="text-[11px] text-zinc-500">{status}</div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {AXIS_ORDER.map((name) => {
            const axis =
              byName.get(name) ??
              ({
                axis: name,
                present: false,
                confidence: null,
                confidence_raw: null,
                updated: null,
                stance: "",
                open_questions: [],
              } as ThesisAxis);
            return (
              <AxisCard
                key={name}
                axis={axis}
                onStressTest={handleStressTest}
                stressing={stressing}
              />
            );
          })}
        </div>

        <Card>
          <CardHeader title="evidence log" subtitle="newest first" />
          <CardBody>
            {evidence.length === 0 ? (
              <p className="text-xs text-zinc-600">
                no evidence rows yet — starts Day 4
              </p>
            ) : (
              <ul className="space-y-1.5">
                {evidence.map((row, i) => (
                  <li
                    key={`${row.date}-${row.axis}-${i}`}
                    className="flex items-baseline gap-3 text-xs"
                  >
                    <span className="shrink-0 font-mono text-[10px] text-zinc-600">
                      {row.date}
                    </span>
                    <span className="shrink-0 text-[10px] uppercase tracking-widest text-zinc-500">
                      {row.axis}
                    </span>
                    <span className="flex-1 truncate text-zinc-300">
                      {row.claim}
                    </span>
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
