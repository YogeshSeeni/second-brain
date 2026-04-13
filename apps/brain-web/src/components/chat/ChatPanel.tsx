"use client";

import { useEffect, useRef, useState } from "react";
import { listMessages, postChat, streamUrl } from "@/lib/api";

type Msg = { role: "user" | "assistant" | "system" | "job"; body: string };
type ToolCall = { index: number; name: string; state: "running" | "done" };

export type ChatPanelProps = {
  initialThreadId?: string | null;
  threadLabel?: string;
};

export default function ChatPanel({
  initialThreadId = null,
  threadLabel = "main thread",
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(initialThreadId);
  const [tools, setTools] = useState<ToolCall[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(Boolean(initialThreadId));
  const scrollRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setThreadId(initialThreadId);
    setMessages([]);
    setTools([]);
    setLoadingHistory(Boolean(initialThreadId));
    if (!initialThreadId) return;
    let active = true;
    (async () => {
      try {
        const rows = await listMessages(initialThreadId);
        if (!active) return;
        setMessages(
          rows.map((r) => ({ role: r.role, body: r.body })),
        );
      } catch {
        /* ignore — empty history is fine */
      } finally {
        if (active) setLoadingHistory(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [initialThreadId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => () => esRef.current?.close(), []);

  async function send() {
    const body = input.trim();
    if (!body) return;
    esRef.current?.close();
    esRef.current = null;
    setInput("");
    setMessages((m) => [...m, { role: "user", body }, { role: "assistant", body: "" }]);
    setTools([]);
    setStreaming(true);
    try {
      const { task_id, thread_id } = await postChat(body, threadId);
      setThreadId(thread_id);
      const es = new EventSource(streamUrl(task_id));
      esRef.current = es;
      es.addEventListener("delta", (e) => {
        const chunk = (e as MessageEvent).data as string;
        setMessages((m) => {
          const copy = m.slice();
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") {
            copy[copy.length - 1] = { role: "assistant", body: last.body + chunk };
          }
          return copy;
        });
      });
      es.addEventListener("tool", (e) => {
        try {
          const payload = JSON.parse((e as MessageEvent).data as string) as {
            event: "start" | "stop";
            name?: string;
            index: number;
          };
          setTools((prev) => {
            if (payload.event === "start") {
              return [
                ...prev,
                { index: payload.index, name: payload.name ?? "tool", state: "running" },
              ];
            }
            return prev.map((t) =>
              t.index === payload.index ? { ...t, state: "done" } : t,
            );
          });
        } catch {
          /* ignore malformed tool event */
        }
      });
      es.addEventListener("done", () => {
        es.close();
        if (esRef.current === es) {
          esRef.current = null;
          setStreaming(false);
        }
      });
      es.addEventListener("error", () => {
        es.close();
        if (esRef.current === es) {
          esRef.current = null;
          setStreaming(false);
        }
      });
    } catch (err) {
      setMessages((m) => {
        const copy = m.slice();
        const last = copy[copy.length - 1];
        const errBody = `[error] ${(err as Error).message}`;
        if (last?.role === "assistant" && last.body === "") {
          copy[copy.length - 1] = { role: "assistant", body: errBody };
        } else {
          copy.push({ role: "assistant", body: errBody });
        }
        return copy;
      });
      setStreaming(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="border-b border-zinc-900 px-4 py-2 text-[11px] uppercase tracking-widest text-zinc-500">
          {threadLabel}
        </div>
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {loadingHistory && (
            <p className="text-xs text-zinc-600">loading history…</p>
          )}
          {!loadingHistory && messages.length === 0 && (
            <p className="text-xs text-zinc-600">type a message to begin</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className="mb-4">
              <div className="mb-1 text-[10px] uppercase tracking-widest text-zinc-500">
                {m.role}
              </div>
              <div className="whitespace-pre-wrap text-sm leading-6 text-zinc-100">
                {m.body}
                {streaming && i === messages.length - 1 && m.role === "assistant" && (
                  <span className="ml-1 inline-block h-3 w-2 animate-pulse bg-zinc-400 align-middle" />
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-zinc-900 p-3">
          <textarea
            className="w-full resize-none rounded border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
            placeholder={
              streaming
                ? "streaming… (enter to interrupt and send a new turn)"
                : "message (enter to send, shift+enter for newline)"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
          />
        </div>
      </div>
      <aside className="hidden w-60 shrink-0 border-l border-zinc-900 bg-zinc-950/40 md:block">
        <div className="border-b border-zinc-900 px-4 py-2 text-[11px] uppercase tracking-widest text-zinc-500">
          agent activity
        </div>
        <div className="px-4 py-3">
          {tools.length === 0 ? (
            <p className="text-xs text-zinc-600">no tool calls yet</p>
          ) : (
            <ul className="space-y-1.5">
              {tools.map((t, i) => (
                <li
                  key={`${t.index}-${i}`}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className={`inline-block h-1.5 w-1.5 rounded-full ${
                      t.state === "running"
                        ? "animate-pulse bg-amber-400"
                        : "bg-emerald-500"
                    }`}
                  />
                  <span className="truncate font-mono text-zinc-300">{t.name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
