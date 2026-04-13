import { auth, signOut } from "@/auth";
import { QuickCapture } from "./QuickCapture";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "still up, yogesh";
  if (h < 12) return "good morning, yogesh";
  if (h < 17) return "good afternoon, yogesh";
  if (h < 22) return "good evening, yogesh";
  return "good night, yogesh";
}

export async function TopBar() {
  const session = await auth();
  const email = session?.user?.email ?? null;

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-zinc-900 bg-zinc-950/80 px-4">
      <div className="text-sm text-zinc-300">{greeting()}</div>
      <div className="h-4 w-px bg-zinc-800" />
      <QuickCapture />
      <div className="ml-auto flex items-center gap-3 text-xs text-zinc-500">
        {email ? (
          <>
            <span className="hidden truncate sm:inline">{email}</span>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/signin" });
              }}
            >
              <button
                type="submit"
                className="rounded border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
              >
                sign out
              </button>
            </form>
          </>
        ) : null}
      </div>
    </header>
  );
}
