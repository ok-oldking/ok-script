import type { AutomationTask, ExecutorStatus } from "./types";
import { t } from "./i18n";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const message = "detail" in (body as object)
      ? (body as { detail?: string }).detail
      : response.statusText;
    throw new Error(message || t("Request failed"));
  }
  return body as T;
}

export const runtimeApi = {
  status: () => request<ExecutorStatus>("/api/status"),
  tasks: () => request<AutomationTask[]>("/api/tasks"),
  startTask: (name: string) => request<AutomationTask>(
    `/api/tasks/${encodeURIComponent(name)}/start`,
    { method: "POST" }
  ),
  pause: () => request<ExecutorStatus>("/api/executor/pause", { method: "POST" }),
  resume: () => request<ExecutorStatus>("/api/executor/resume", { method: "POST" }),
  stopTask: () => request<ExecutorStatus>("/api/executor/stop-task", { method: "POST" })
};
