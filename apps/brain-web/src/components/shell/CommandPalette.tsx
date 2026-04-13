"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useRouter } from "next/navigation";
import {
  createThread,
  postCapture,
  runJob,
  listJobs,
  type JobSummary,
} from "@/lib/api";

type Action = {
  id: string;
  label: string;
  hint?: string;
  section: "nav" | "capture" | "threads" | "jobs";
  run: () => Promise<void> | void;
};

const NAV_ROUTES: Array<{ id: string; label: string; path: string }> = [
  { id: "nav-today", label: "Go to today", path: "/" },
  { id: "nav-chat", label: "Go to chat", path: "/chat" },
  { id: "nav-capture", label: "Go to capture", path: "/capture" },
  { id: "nav-inbox", label: "Go to inbox", path: "/inbox" },
  { id: "nav-thesis", label: "Go to thesis", path: "/thesis" },
  { id: "nav-jobs", label: "Go to jobs", path: "/jobs" },
  { id: "nav-wiki", label: "Go to wiki", path: "/wiki" },
  { id: "nav-settings", label: "Go to settings", path: "/settings" },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [mode, setMode] = useState<null | "capture" | "thread">(null);
  const [freeText, setFreeText] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Global keybinding: Cmd/Ctrl+K toggles.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        e.preventDefault();
        reset();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Load jobs list the first time the palette opens.
  useEffect(() => {
    if (!open || jobs.length > 0) return;
    listJobs()
      .then(setJobs)
      .catch(() => setJobs([]));
  }, [open, jobs.length]);

  // Focus input whenever the palette or its sub-mode changes.
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open, mode]);

  const reset = useCallback(() => {
    setOpen(false);
    setQuery("");
    setCursor(0);
    setMode(null);
    setFreeText("");
    setFlash(null);
    setBusy(false);
  }, []);

  const actions = useMemo<Action[]>(() => {
    const navActions: Action[] = NAV_ROUTES.map((r) => ({
      id: r.id,
      label: r.label,
      section: "nav",
      run: () => {
        router.push(r.path);
        reset();
      },
    }));
    const captureAction: Action = {
      id: "capture-inline",
      label: "Quick capture…",
      hint: "note, url, or thought",
      section: "capture",
      run: () => {
        setMode("capture");
        setFreeText("");
        setQuery("");
      },
    };
    const threadAction: Action = {
      id: "thread-new",
      label: "New topic thread…",
      hint: "spawn a focused chat",
      section: "threads",
      run: () => {
        setMode("thread");
        setFreeText("");
        setQuery("");
      },
    };
    const jobActions: Action[] = jobs.map((j) => ({
      id: `job-${j.name}`,
      label: `Run job: ${j.name}`,
      hint: j.schedule ?? "ad-hoc",
      section: "jobs",
      run: async () => {
        setBusy(true);
        try {
          await runJob(j.name);
          setFlash(`queued: ${j.name}`);
        } catch (e) {
          setFlash(`error: ${(e as Error).message}`);
        } finally {
          setBusy(false);
          setTimeout(reset, 900);
        }
      },
    }));
    return [captureAction, threadAction, ...navActions, ...jobActions];
  }, [jobs, router, reset]);

  const filtered = useMemo(() => {
    if (mode) return [];
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter((a) =>
      (a.label + " " + (a.hint ?? "")).toLowerCase().includes(q),
    );
  }, [actions, query, mode]);

  useEffect(() => {
    if (cursor >= filtered.length) setCursor(0);
  }, [filtered.length, cursor]);

  async function runFreeText() {
    const text = freeText.trim();
    if (!text || busy) return;
    setBusy(true);
    setFlash(null);
    try {
      if (mode === "capture") {
        const res = await postCapture(text);
        setFlash(`filed → ${res.target_path}`);
        setTimeout(reset, 900);
      } else if (mode === "thread") {
        const t = await createThread(text);
        router.push(`/chat/${t.id}`);
        reset();
      }
    } catch (e) {
      setFlash(`error: ${(e as Error).message}`);
      setBusy(false);
    }
  }

  function onListKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const action = filtered[cursor];
      if (action) action.run();
    }
  }

  function onFreeTextKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      runFreeText();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setMode(null);
      setQuery("");
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-24"
      onClick={reset}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 shadow-2xl"
      >
        {mode === null ? (
          <>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setCursor(0);
              }}
              onKeyDown={onListKey}
              placeholder="type a command…"
              className="h-11 w-full border-b border-zinc-800 bg-transparent px-4 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none"
            />
            <ul className="max-h-80 overflow-y-auto">
              {filtered.length === 0 && (
                <li className="px-4 py-3 text-xs text-zinc-600">no match</li>
              )}
              {filtered.map((a, i) => (
                <li
                  key={a.id}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => a.run()}
                  className={`flex cursor-pointer items-baseline gap-2 px-4 py-2 text-sm ${
                    i === cursor ? "bg-zinc-900" : ""
                  }`}
                >
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-zinc-400">
                    {a.section}
                  </span>
                  <span className="flex-1 text-zinc-200">{a.label}</span>
                  {a.hint && (
                    <span className="text-[11px] text-zinc-600">{a.hint}</span>
                  )}
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-zinc-900 px-4 py-1.5 text-[10px] uppercase tracking-widest text-zinc-600">
              <span>↑↓ select · ⏎ run · esc close</span>
              {flash && <span className="normal-case text-zinc-500">{flash}</span>}
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-2 text-[10px] uppercase tracking-widest text-zinc-500">
              {mode === "capture" ? "quick capture" : "new topic thread"}
            </div>
            <input
              ref={inputRef}
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              onKeyDown={onFreeTextKey}
              disabled={busy}
              placeholder={
                mode === "capture"
                  ? "note, url, or thought…"
                  : "thread title — e.g. citadel quant infra"
              }
              className="h-11 w-full bg-transparent px-4 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none disabled:opacity-60"
            />
            <div className="flex items-center justify-between border-t border-zinc-900 px-4 py-1.5 text-[10px] uppercase tracking-widest text-zinc-600">
              <span>⏎ {busy ? "working…" : mode === "capture" ? "file it" : "spawn"} · esc back</span>
              {flash && <span className="normal-case text-zinc-500">{flash}</span>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
