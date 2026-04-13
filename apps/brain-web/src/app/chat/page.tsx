import ChatClient from "@/components/ChatClient";

export const metadata = {
  title: "brain / chat",
};

export default function ChatPage() {
  return (
    <main className="flex h-dvh flex-col bg-black text-zinc-100 font-mono">
      <header className="border-b border-zinc-800 px-4 py-2 text-xs uppercase tracking-widest text-zinc-500">
        brain · main thread
      </header>
      <ChatClient />
    </main>
  );
}
