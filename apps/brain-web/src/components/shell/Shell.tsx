import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { StatusFooter } from "./StatusFooter";
import { NudgeBanner } from "./NudgeBanner";
import { CommandPalette } from "./CommandPalette";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh min-h-0 w-full flex-col bg-black text-zinc-100">
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <NudgeBanner />
          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
      <StatusFooter />
      <CommandPalette />
    </div>
  );
}
