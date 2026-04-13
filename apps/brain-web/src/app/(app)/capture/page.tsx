"use client";

import { useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { postCapture, type CaptureResponse } from "@/lib/api";

type Entry = { body: string; response: CaptureResponse | null; error?: string };

export default function CapturePage() {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Entry[]>([]);

  async function submit() {
    const text = body.trim();
    if (!text || busy) return;
    setBusy(true);
    const entry: Entry = { body: text, response: null };
    setHistory((h) => [entry, ...h]);
    try {
      const res = await postCapture(text);
      setHistory((h) =>
        h.map((e, i) => (i === 0 ? { ...e, response: res } : e)),
      );
      setBody("");
    } catch (err) {
      setHistory((h) =>
        h.map((e, i) => (i === 0 ? { ...e, error: (err as Error).message } : e)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-2xl space-y-4">
        <Card>
          <CardHeader
            title="capture"
            subtitle="note, url, or thought — agent classifies and files"
          />
          <CardBody>
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              disabled={busy}
              rows={5}
              placeholder="paste a url, jot a note, or dump a thought…"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-zinc-600">⌘+enter to file</span>
              <Button onClick={submit} disabled={busy || !body.trim()}>
                {busy ? "filing…" : "file it"}
              </Button>
            </div>
          </CardBody>
        </Card>

        {history.length > 0 && (
          <div>
            <div className="mb-2 px-1 text-[11px] uppercase tracking-widest text-zinc-600">
              recent captures
            </div>
            <ul className="space-y-2">
              {history.map((e, i) => (
                <li key={i}>
                  <Card>
                    <CardBody>
                      <div className="text-xs text-zinc-400">{e.body}</div>
                      <div className="mt-2 flex items-center gap-2">
                        {e.error ? (
                          <Badge tone="error">error</Badge>
                        ) : e.response ? (
                          <>
                            <Badge tone="ok">{e.response.kind}</Badge>
                            <span className="truncate font-mono text-[11px] text-zinc-500">
                              {e.response.target_path}
                            </span>
                          </>
                        ) : (
                          <Badge tone="info">filing…</Badge>
                        )}
                      </div>
                      {e.error && (
                        <div className="mt-1 font-mono text-[11px] text-red-400">
                          {e.error}
                        </div>
                      )}
                      {e.response?.summary && (
                        <div className="mt-2 text-[11px] text-zinc-500">
                          {e.response.summary}
                        </div>
                      )}
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
