import type { ActionResult, CaptureUiState, ExecutorStatus, LogResponse } from "./types";
import { t } from "./i18n";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json() as T | { detail?: string }
    : await response.text();
  if (!response.ok) {
    const message = typeof body === "object" && body && "detail" in body
      ? (body as { detail?: string }).detail
      : response.statusText;
    throw new Error(message || t("Request failed"));
  }
  return body as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

export const runtimeApi = {
  captureUi: () => request<CaptureUiState>("/api/ui/capture"),
  pause: () => post<ExecutorStatus>("/api/executor/pause"),
  resume: () => post<ExecutorStatus>("/api/executor/resume"),
  refreshDevices: () => post<{ accepted: boolean }>("/api/devices/refresh"),
  selectDevice: (id: string) => post<CaptureUiState>("/api/devices/select", { id }),
  selectCapture: (id: string) => post<CaptureUiState>("/api/capture-methods/select", { id }),
  selectInteraction: (id: string) => post<CaptureUiState>("/api/interaction-methods/select", { id }),
  setOverlay: (name: "boxes" | "logs", value: boolean) =>
    post<CaptureUiState>("/api/overlay", { name, value }),
  tool: (action: string) => post<ActionResult>(`/api/tools/${encodeURIComponent(action)}`),
  logs: (level = "ALL", query = "") => {
    const parameters = new URLSearchParams({ level, query });
    return request<LogResponse>(`/api/logs?${parameters}`);
  }
};
