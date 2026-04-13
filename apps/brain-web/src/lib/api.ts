export const BRAIN_CORE_URL =
  process.env.NEXT_PUBLIC_BRAIN_CORE_URL ?? "http://localhost:8000";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BRAIN_CORE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export type HealthResponse = { ok: boolean };
export function getHealth(): Promise<HealthResponse> {
  return json("/api/health");
}

export type StartChatResponse = { task_id: number; thread_id: string };
export function postChat(body: string, threadId: string | null): Promise<StartChatResponse> {
  return json("/api/chat", {
    method: "POST",
    body: JSON.stringify({ body, thread_id: threadId }),
  });
}

export function streamUrl(taskId: number): string {
  return `${BRAIN_CORE_URL}/api/chat/stream/${taskId}`;
}

export type CaptureResponse = {
  kind: string;
  target_path: string;
  summary?: string;
};
export function postCapture(body: string): Promise<CaptureResponse> {
  return json("/api/capture", {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export type JobRun = {
  id: number;
  name: string;
  trigger: string;
  started_at: number;
  ended_at: number | null;
  state: "running" | "done" | "error";
  exit_code: number | null;
  files_touched: number | null;
};

export type JobSummary = {
  name: string;
  schedule: string | null;
  last_run: JobRun | null;
};

export function listJobs(): Promise<JobSummary[]> {
  return json("/api/jobs");
}

export function runJob(name: string): Promise<JobRun> {
  return json(`/api/jobs/${encodeURIComponent(name)}/run`, { method: "POST" });
}

export type DashboardResponse = {
  recovery: {
    score: number | null;
    hrv_ms: number | null;
    resting_hr: number | null;
    captured_at: number | null;
  } | null;
  calendar: Array<{
    id: string;
    summary: string;
    start_at: number;
    end_at: number | null;
  }>;
  priorities: string[];
  recent_activity: Array<{
    kind: string;
    label: string;
    at: number;
    state?: string;
  }>;
  nudges: Array<{
    id: number;
    kind: string;
    body: string;
    created_at: number;
  }>;
};

export function getDashboard(): Promise<DashboardResponse> {
  return json("/api/dashboard");
}
