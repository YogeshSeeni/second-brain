"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  badge?: number;
  match?: (path: string) => boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "Today", match: (p) => p === "/" },
  { href: "/chat", label: "Chat", match: (p) => p.startsWith("/chat") },
  { href: "/capture", label: "Capture" },
  { href: "/jobs", label: "Jobs" },
  { href: "/inbox", label: "Inbox" },
  { href: "/thesis", label: "Thesis" },
  { href: "/wiki", label: "Wiki", match: (p) => p.startsWith("/wiki") },
  { href: "/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname() ?? "/";

  return (
    <nav className="flex h-full w-52 shrink-0 flex-col border-r border-zinc-900 bg-zinc-950/80">
      <div className="px-4 py-4">
        <div className="text-xs uppercase tracking-widest text-zinc-600">
          brain
        </div>
        <div className="mt-1 text-sm font-medium text-zinc-200">second brain</div>
      </div>
      <div className="flex-1 px-2">
        <ul className="space-y-0.5">
          {NAV.map((item) => {
            const active = item.match
              ? item.match(pathname)
              : pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center justify-between rounded px-2 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-zinc-900 text-zinc-100"
                      : "text-zinc-400 hover:bg-zinc-900/60 hover:text-zinc-200"
                  }`}
                >
                  <span>{item.label}</span>
                  {item.badge ? (
                    <span className="rounded bg-zinc-800 px-1.5 text-[10px] text-zinc-300">
                      {item.badge}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="border-t border-zinc-900 px-4 py-3">
        <div className="text-[10px] uppercase tracking-widest text-zinc-600">
          runs
        </div>
        <div className="mt-1 text-[11px] text-zinc-500">no active runs</div>
      </div>
    </nav>
  );
}
