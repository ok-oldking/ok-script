export type ExecutorStatus = {
  paused: boolean;
  running: boolean;
  current_task: string | null;
  task_count: number;
  hotkey: string | null;
};

export type DeviceOption = {
  id: string;
  label: string;
  kind: string;
  connected: boolean;
  resolution: string;
  selected: boolean;
  keywords: string;
};

export type MethodOption = {
  id: string;
  label: string;
  selected: boolean;
};

export type CaptureUiState = {
  title: string;
  version: string;
  icon_url: string | null;
  status: ExecutorStatus;
  devices: DeviceOption[];
  capture_methods: MethodOption[];
  interaction_methods: MethodOption[];
  overlay: {
    boxes: boolean;
    logs: boolean;
  };
};

export type ActionResult = {
  ok: boolean;
  message: string;
  kind?: "capture" | "ocr" | "folder" | "export";
  resource_url?: string;
};

export type LogResponse = {
  path: string;
  text: string;
  line_count: number;
  modified: number | null;
};

export type RuntimeEvent = {
  event: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
};
