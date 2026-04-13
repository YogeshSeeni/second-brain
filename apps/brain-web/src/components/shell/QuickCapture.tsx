"use client";

import { useState } from "react";
import { postCapture } from "@/lib/api";

export function QuickCapture() {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = value.trim();
    if (!body || busy) return;
    setBusy(true);
    setFlash(null);
    try {
      const res = await postCapture(body);
      setFlash(`filed → ${res.target_path}`);
      setValue("");
    } catch (err) {
      setFlash(`error: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="relative flex-1 max-w-xl">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
        placeholder={busy ? "filing…" : "quick capture — note, url, or thought"}
        className="h-8 w-full rounded border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-zinc-500 disabled:opacity-60"
      />
      {flash && (
        <div className="pointer-events-none absolute left-0 right-0 top-full mt-1 truncate text-[11px] text-zinc-500">
          {flash}
        </div>
      )}
    </form>
  );
}
