import { ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { BRAIN_CORE_URL } from "@/lib/api";

export const metadata = { title: "brain / chat / topic" };

type Props = { params: Promise<{ threadId: string }> };

async function fetchThreadLabel(threadId: string): Promise<string> {
  try {
    const res = await fetch(`${BRAIN_CORE_URL}/api/threads`, {
      cache: "no-store",
    });
    if (!res.ok) return threadId.slice(0, 6);
    const rows = (await res.json()) as Array<{
      id: string;
      title: string | null;
    }>;
    const hit = rows.find((r) => r.id === threadId);
    return hit?.title ?? threadId.slice(0, 6);
  } catch {
    return threadId.slice(0, 6);
  }
}

export default async function ThreadChatPage(props: Props) {
  const { threadId } = await props.params;
  const label = await fetchThreadLabel(threadId);
  return <ChatWorkspace threadId={threadId} threadLabel={label} />;
}
