import ChatPanel from "@/components/chat/ChatPanel";
import { ThreadList } from "@/components/chat/ThreadList";

export function ChatWorkspace({
  threadId = null,
  threadLabel,
}: {
  threadId?: string | null;
  threadLabel?: string;
}) {
  return (
    <div className="flex h-full min-h-0 flex-row">
      <ThreadList activeThreadId={threadId} />
      <div className="min-h-0 min-w-0 flex-1">
        <ChatPanel initialThreadId={threadId} threadLabel={threadLabel} />
      </div>
    </div>
  );
}
