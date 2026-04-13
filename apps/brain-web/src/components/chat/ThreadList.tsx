"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createThread, listThreads, type Thread } from "@/lib/api";

function relativeTime(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export function ThreadList({ activeThreadId }: { activeThreadId: string | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    try {
      const rows = await listThreads();
      setThreads(rows);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    reload();
    const id = setInterval(reload, 30_000);
    return () => clearInterval(id);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = title.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const t = await createThread(name);
      setTitle("");
      await reload();
      router.push(`/chat/${t.id}`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  const mainThreads = threads.filter((t) => t.kind === "main");
  const topicThreads = threads.filter((t) => t.kind === "topic");
  const mainHref = "/chat";
  const isMainActive =
    pathname === "/chat" ||
    (activeThreadId != null &&
      mainThreads.some((m) => m.id === activeThreadId));

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-zinc-900 bg-zinc-950/40 md:flex">
      <div className="border-b border-zinc-900 px-4 py-2 text-[11px] uppercase tracking-widest text-zinc-500">
        threads
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ul className="py-2">
          <li>
            <Link
              href={mainHref}
              className={`block px-4 py-1.5 text-xs transition ${
                isMainActive
                  ? "bg-zinc-900 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-900/50 hover:text-zinc-200"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate">main</span>
                <span className="text-[10px] text-zinc-600">always</span>
              </div>
            </Link>
          </li>
        </ul>
        {topicThreads.length > 0 && (
          <>
            <div className="mt-2 px-4 text-[10px] uppercase tracking-widest text-zinc-600">
              topics
            </div>
            <ul className="py-1">
              {topicThreads.map((t) => {
                const active = t.id === activeThreadId;
                return (
                  <li key={t.id}>
                    <Link
                      href={`/chat/${t.id}`}
                      className={`block px-4 py-1.5 text-xs transition ${
                        active
                          ? "bg-zinc-900 text-zinc-100"
                          : "text-zinc-400 hover:bg-zinc-900/50 hover:text-zinc-200"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">{t.title ?? t.id.slice(0, 6)}</span>
                        <span className="shrink-0 text-[10px] text-zinc-600">
                          {relativeTime(t.updated_at)}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
      <form
        onSubmit={handleCreate}
        className="border-t border-zinc-900 px-3 py-3"
      >
        <div className="text-[10px] uppercase tracking-widest text-zinc-600">
          new topic
        </div>
        <input
          type="text"
          className="mt-1 w-full rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-zinc-600"
          placeholder="topic title…"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={creating}
        />
        <button
          type="submit"
          disabled={creating || !title.trim()}
          className="mt-2 w-full rounded border border-zinc-700 px-2 py-1 text-[10px] uppercase tracking-widest text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200 disabled:opacity-40"
        >
          {creating ? "creating…" : "create"}
        </button>
        {err && (
          <div className="mt-1 font-mono text-[10px] text-zinc-600">{err}</div>
        )}
      </form>
    </aside>
  );
}
