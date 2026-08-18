import type { AboutInfo, ActionResult, AutomationTask, CaptureUiState, ExecutorStatus, LogResponse, NavigationCapabilities, ScheduleData, ScriptDocument, ScriptSummary, ScriptTemplate, SettingsGroup, TaskTabManifest, TemplateAnnotations, TemplateImage, ThemeUiState, UpdateApplyResult, UpdateCheckResult } from "./types";
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

async function checkedResponse(response: Response) {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({})) as { detail?: string };
  throw new Error(body.detail || response.statusText || t("Request failed"));
}

export const runtimeApi = {
  contentReady: () => post<{ ready: boolean }>("/api/ui/ready"),
  captureUi: () => request<CaptureUiState>("/api/ui/capture"),
  themeUi: () => request<ThemeUiState>("/api/ui/theme"),
  pause: () => post<ExecutorStatus>("/api/executor/pause"),
  resume: () => post<ExecutorStatus>("/api/executor/resume"),
  refreshDevices: () => post<{ accepted: boolean }>("/api/devices/refresh"),
  selectDevice: (id: string) => post<CaptureUiState>("/api/devices/select", { id }),
  selectCapture: (id: string) => post<CaptureUiState>("/api/capture-methods/select", { id }),
  selectInteraction: (id: string) => post<CaptureUiState>("/api/interaction-methods/select", { id }),
  setOverlay: (name: "boxes", value: boolean) =>
    post<CaptureUiState>("/api/overlay", { name, value }),
  tasks: () => request<AutomationTask[]>("/api/tasks"),
  settings: () => request<SettingsGroup[]>("/api/settings"),
  navigation: () => request<NavigationCapabilities>("/api/navigation"),
  taskTabs: () => request<TaskTabManifest[]>("/api/task-tabs"),
  taskTabQuery: <T>(tabId: string, operation: string, body: Record<string, unknown> = {}) =>
    post<T>(`/api/task-tabs/${encodeURIComponent(tabId)}/query/${encodeURIComponent(operation)}`, body),
  taskTabAction: <T>(tabId: string, operation: string, body: Record<string, unknown> = {}) =>
    post<T>(`/api/task-tabs/${encodeURIComponent(tabId)}/action/${encodeURIComponent(operation)}`, body),
  about: () => request<AboutInfo>("/api/about"),
  updates: (releaseOnly = true) => request<UpdateCheckResult>(`/api/updates?release_only=${releaseOnly}`),
  applyUpdate: (version: string) => post<UpdateApplyResult>("/api/updates/apply", { version }),
  scripts: () => request<ScriptSummary[]>("/api/scripts"),
  scriptTemplates: () => request<ScriptTemplate[]>("/api/script-templates"),
  script: (name: string) => request<ScriptDocument>(`/api/scripts/${encodeURIComponent(name)}`),
  createScript: (className: string, taskName: string, description: string) =>
    post<ScriptDocument>("/api/scripts", { class_name: className, task_name: taskName, description }),
  saveScript: (name: string, code: string) => post<ScriptDocument>(`/api/scripts/${encodeURIComponent(name)}`, { code }),
  deleteScript: (name: string) => post<{ deleted: string }>(`/api/scripts/${encodeURIComponent(name)}/delete`),
  copyScript: (name: string) => post<ScriptDocument>(`/api/scripts/${encodeURIComponent(name)}/copy`),
  runScript: (name: string, code: string) => post<ScriptDocument>(`/api/scripts/${encodeURIComponent(name)}/run`, { code }),
  scriptExportOptions: () => request<{ tasks: string[]; manifest: Record<string, string> }>("/api/scripts-export/options"),
  exportScripts: async (selected: string[], fileName: string, scriptName: string, version: string) => {
    const response = await checkedResponse(await fetch("/api/scripts-export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected, file_name: fileName, script_name: scriptName, version })
    }));
    return response.blob();
  },
  importScripts: (file: File) => request<{ message: string }>("/api/scripts-import", {
    method: "POST", headers: { "Content-Type": "application/octet-stream", "X-File-Name": file.name }, body: file
  }),
  startScriptRecording: () => post<{ recording: boolean; target?: string }>("/api/scripts-record/start"),
  stopScriptRecording: (code: string, loop: "none" | "count" | "forever", count: number) => post<{ recording: boolean; code: string }>("/api/scripts-record/stop", { code, loop, count }),
  templates: () => request<TemplateImage[]>("/api/templates"),
  captureTemplate: () => post<TemplateImage[]>("/api/templates/capture"),
  deleteTemplate: (name: string) => post<{ deleted: string }>(`/api/templates/${encodeURIComponent(name)}/delete`),
  templateAnnotations: (name: string) => request<TemplateAnnotations>(`/api/templates/${encodeURIComponent(name)}/annotations`),
  saveTemplateAnnotations: (name: string, annotations: TemplateAnnotations["annotations"]) => post<TemplateAnnotations>(`/api/templates/${encodeURIComponent(name)}/annotations`, { annotations }),
  saveTemplates: (destination: "tasks" | "assets", generateLabelEnum: boolean, enumPath: string) => post<{ message: string }>("/api/templates/save", { destination, generate_label_enum: generateLabelEnum, enum_path: enumPath }),
  schedule: () => request<ScheduleData>("/api/schedule"),
  createSchedule: (body: Record<string, unknown>) => post<ScheduleData>("/api/schedule", body),
  scheduleAction: (name: string, action: "enable" | "disable" | "delete") =>
    post<ScheduleData>(`/api/schedule/${encodeURIComponent(name)}/action`, { action }),
  updateSchedule: (name: string, body: Record<string, unknown>) => post<ScheduleData>(`/api/schedule/${encodeURIComponent(name)}`, body),
  setSetting: (group: string, key: string, value: unknown) =>
    post<SettingsGroup>(`/api/settings/${encodeURIComponent(group)}/config`, { key, value }),
  resetSettings: (group: string) =>
    post<SettingsGroup>(`/api/settings/${encodeURIComponent(group)}/reset`),
  startTask: (name: string) => post<AutomationTask>(`/api/tasks/${encodeURIComponent(name)}/start`),
  taskAction: (name: string, action: "enable" | "disable" | "pause" | "resume" | "stop") =>
    post<AutomationTask>(`/api/tasks/${encodeURIComponent(name)}/action`, { action }),
  setTaskConfig: (name: string, key: string, value: unknown) =>
    post<AutomationTask>(`/api/tasks/${encodeURIComponent(name)}/config`, { key, value }),
  resetTaskConfig: (name: string) =>
    post<AutomationTask>(`/api/tasks/${encodeURIComponent(name)}/config/reset`),
  stopTask: () => post<ExecutorStatus>("/api/executor/stop-task"),
  tool: (action: string) => post<ActionResult>(`/api/tools/${encodeURIComponent(action)}`),
  logs: (level = "ALL", query = "") => {
    const parameters = new URLSearchParams({ level, query });
    return request<LogResponse>(`/api/logs?${parameters}`);
  }
};
