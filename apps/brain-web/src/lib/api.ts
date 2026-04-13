export const BRAIN_CORE_URL =
  process.env.NEXT_PUBLIC_BRAIN_CORE_URL ?? "http://localhost:8000";

export type StartChatResponse = {
  task_id: number;
  thread_id: string;
};

export async function postChat(
  body: string,
  threadId: string | null,
): Promise<StartChatResponse> {
  const res = await fetch(`${BRAIN_CORE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, thread_id: threadId }),
  });
  if (!res.ok) {
    throw new Error(`chat POST failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as StartChatResponse;
}

export function streamUrl(taskId: number): string {
  return `${BRAIN_CORE_URL}/api/chat/stream/${taskId}`;
}
