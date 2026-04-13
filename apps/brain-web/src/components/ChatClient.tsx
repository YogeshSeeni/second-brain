"use client";

import { useEffect, useRef, useState } from "react";
import { postChat, streamUrl } from "@/lib/api";

type Msg = { role: "user" | "assistant"; body: string };

export default function ChatClient() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function send() {
    const body = input.trim();
    if (!body || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", body }, { role: "assistant", body: "" }]);
    setStreaming(true);
    try {
      const { task_id, thread_id } = await postChat(body, threadId);
      setThreadId(thread_id);
      const es = new EventSource(streamUrl(task_id));
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
      es.addEventListener("done", () => {
        es.close();
        setStreaming(false);
      });
      es.addEventListener("error", () => {
        es.close();
        setStreaming(false);
      });
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", body: `[error] ${(err as Error).message}` },
      ]);
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
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
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
      <div className="border-t border-zinc-800 p-3">
        <textarea
          className="w-full resize-none rounded border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
          placeholder={streaming ? "…" : "message (enter to send, shift+enter for newline)"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={streaming}
          rows={2}
        />
      </div>
    </div>
  );
}
