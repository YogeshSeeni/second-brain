"use client";

import { useRef, useState, type DragEvent } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  postCapture,
  postCaptureFile,
  type CaptureFileResponse,
  type CaptureResponse,
} from "@/lib/api";

type TextEntry = {
  mode: "text";
  body: string;
  response: CaptureResponse | null;
  error?: string;
};

type FileEntry = {
  mode: "file";
  filename: string;
  size: number;
  response: CaptureFileResponse | null;
  error?: string;
};

type Entry = TextEntry | FileEntry;

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CapturePage() {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Entry[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function submitText() {
    const text = body.trim();
    if (!text || busy) return;
    setBusy(true);
    const entry: TextEntry = { mode: "text", body: text, response: null };
    setHistory((h) => [entry, ...h]);
    try {
      const res = await postCapture(text);
      setHistory((h) =>
        h.map((e, i) =>
          i === 0 && e.mode === "text" ? { ...e, response: res } : e,
        ),
      );
      setBody("");
    } catch (err) {
      setHistory((h) =>
        h.map((e, i) =>
          i === 0 && e.mode === "text"
            ? { ...e, error: (err as Error).message }
            : e,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitFiles(files: FileList | null) {
    if (!files || files.length === 0 || busy) return;
    setBusy(true);
    // Sequentially upload — keeps ordering in the history list stable.
    for (const f of Array.from(files)) {
      const entry: FileEntry = {
        mode: "file",
        filename: f.name,
        size: f.size,
        response: null,
      };
      setHistory((h) => [entry, ...h]);
      try {
        const res = await postCaptureFile(f);
        setHistory((h) =>
          h.map((e, i) =>
            i === 0 && e.mode === "file" && e.filename === f.name
              ? { ...e, response: res }
              : e,
          ),
        );
      } catch (err) {
        setHistory((h) =>
          h.map((e, i) =>
            i === 0 && e.mode === "file" && e.filename === f.name
              ? { ...e, error: (err as Error).message }
              : e,
          ),
        );
      }
    }
    setBusy(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    submitFiles(e.dataTransfer.files);
  }

  return (
    <div
      className="h-full overflow-y-auto px-6 py-6"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <div className="mx-auto max-w-2xl space-y-4">
        <Card>
          <CardHeader
            title="capture"
            subtitle="note, url, file, or thought — agent classifies and files"
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
                  submitText();
                }
              }}
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-zinc-600">⌘+enter to file</span>
              <Button onClick={submitText} disabled={busy || !body.trim()}>
                {busy ? "filing…" : "file it"}
              </Button>
            </div>

            <div
              className={`mt-4 rounded border border-dashed px-4 py-6 text-center transition-colors ${
                dragOver
                  ? "border-zinc-400 bg-zinc-900/60 text-zinc-200"
                  : "border-zinc-800 text-zinc-500"
              }`}
            >
              <div className="text-xs">
                drop a file here — pdf, image, csv, text, audio
              </div>
              <div className="mt-1 text-[10px] text-zinc-600">
                raw asset goes to <code>raw/</code>, summary stub to{" "}
                <code>wiki/sources/</code>
              </div>
              <div className="mt-3">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={busy}
                  className="rounded border border-zinc-700 px-3 py-1 text-[11px] uppercase tracking-widest text-zinc-300 hover:border-zinc-500 hover:text-zinc-100 disabled:opacity-40"
                >
                  choose file
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={(e) => submitFiles(e.target.files)}
                  className="hidden"
                />
              </div>
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
                      {e.mode === "text" ? (
                        <>
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
                        </>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 text-xs">
                            <Badge tone="info">file</Badge>
                            <span className="truncate text-zinc-300">
                              {e.filename}
                            </span>
                            <span className="shrink-0 text-zinc-600">
                              {fmtBytes(e.size)}
                            </span>
                          </div>
                          {e.response ? (
                            <div className="mt-2 space-y-1 font-mono text-[11px] text-zinc-500">
                              <div>raw → {e.response.raw_path}</div>
                              <div>summary → {e.response.summary_path}</div>
                              {e.response.classified && (
                                <div className="text-zinc-400">
                                  {e.response.summary}
                                </div>
                              )}
                            </div>
                          ) : e.error ? (
                            <div className="mt-1 font-mono text-[11px] text-red-400">
                              {e.error}
                            </div>
                          ) : (
                            <div className="mt-2 text-[11px] text-zinc-600">
                              uploading…
                            </div>
                          )}
                        </>
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
