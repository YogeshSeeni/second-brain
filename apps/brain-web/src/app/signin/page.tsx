import { signIn } from "@/auth";
import { Button } from "@/components/ui/Button";

export const metadata = {
  title: "brain / sign in",
};

export default function SignInPage() {
  return (
    <div className="flex h-dvh items-center justify-center bg-black text-zinc-100">
      <div className="w-full max-w-sm rounded border border-zinc-800 bg-zinc-950 p-6">
        <div className="text-xs uppercase tracking-widest text-zinc-600">brain</div>
        <div className="mt-1 text-lg text-zinc-100">second brain</div>
        <p className="mt-4 text-sm text-zinc-500">
          single-user control panel. sign in with the allowlisted google account.
        </p>
        <form
          className="mt-6"
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: "/" });
          }}
        >
          <Button type="submit" className="w-full">
            continue with google
          </Button>
        </form>
      </div>
    </div>
  );
}
