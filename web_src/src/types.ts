export type ExecutorStatus = {
  paused: boolean;
  running: boolean;
  starting: boolean;
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
  debug: boolean;
  event_session_key: string;
  icon_url: string | null;
  status: ExecutorStatus;
  devices: DeviceOption[];
  capture_methods: MethodOption[];
  interaction_methods: MethodOption[];
  overlay: {
    boxes: boolean;
  };
};

export type ThemeUiState = {
  system_accent: {
    light: string;
    dark: string;
  } | null;
};

export type ActionResult = {
  ok: boolean;
  message: string;
  kind?: "capture" | "ocr" | "folder" | "export";
  resource_url?: string;
};

export type AutomationTask = {
  name: string;
  class_name: string;
  enabled: boolean;
  running: boolean;
  paused: boolean;
  trigger: boolean;
  description: string;
  visible: boolean;
  group_name: string | null;
  instructions: string | null;
  waiting_for: string | null;
  start_time: number;
  info: Record<string, unknown>;
  config: TaskConfigField[];
};

export type TaskConfigField = {
  key: string;
  value: unknown;
  default: unknown;
  description: string;
  kind: "boolean" | "integer" | "number" | "text" | "multiline" | "file" | "select" | "multi_selection" | "list";
  options: unknown[] | null;
  allow_duplication: boolean;
  minimum: number | null;
  maximum: number | null;
  sub_config: boolean;
};

export type SettingsGroup = {
  name: string;
  description: string;
  expanded: boolean;
  top_level: boolean;
  fields: TaskConfigField[];
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
  ui?: CaptureUiState;
};

export type NavigationCapabilities = {
  triggers: boolean;
  tasks: boolean;
  script: boolean;
  templates: boolean;
  schedule: boolean;
  task_tabs: TaskTabManifest[];
};

export type TaskTabManifest = {
  id: string;
  name: string;
  icon: string;
  position: "scroll" | "bottom";
  add_after_default_tabs: boolean;
  task_controls: boolean;
  task_name: string;
  task_class_name: string;
  module_url: string;
};

export type TaskTabEvent = {
  tab_id: string;
  name: string;
  payload: unknown;
};

export type AboutInfo = {
  title: string;
  version: string;
  debug: boolean;
  icon_url: string | null;
  about: string;
  links: Record<string, unknown>;
  projects: Array<{ name: string; url: string; website?: string }>;
  update_supported: boolean;
  update_check_delay_ms: number;
};

export type AppVersion = { version: string; notes: string[] };
export type UpdateCheckResult = {
  current_version: string;
  versions: AppVersion[];
  update_available: boolean;
};
export type UpdateApplyResult = { accepted: boolean; version: string; result: unknown };

export type ScriptSummary = { name: string; modified: number };
export type ScriptDocument = ScriptSummary & { code: string; error?: string | null };
export type ScriptTemplate = {
  name: string;
  template_name: string;
  category: string;
  doc: string;
  full_doc: string;
  class_name: string;
  is_static: boolean;
  params: Array<{ name: string; default: string | null; doc?: string }>;
};

export type TemplateImage = {
  name: string;
  url: string;
  modified: number;
  categories: string[];
};
export type TemplateAnnotations = {
  name: string;
  url: string;
  width: number;
  height: number;
  annotations: Array<{ id?: number; category: string; bbox: number[] }>;
};

export type ScheduledTask = {
  name: string;
  path: string;
  enabled: boolean;
  status: string;
  trigger_type: string;
  next_run_time: string;
  last_run_time: string;
  description: string;
  task_index: number;
  interval_days: number;
  interval_hours: number;
  start_hour?: number;
  start_minute?: number;
  timeout_hours?: number;
  auto_exit?: boolean;
  read_only: boolean;
};

export type ScheduleData = {
  available_tasks: Array<{ index: number; name: string }>;
  tasks: ScheduledTask[];
};

export type EventRecord = RuntimeEvent & {
  id: number;
  timestamp: Date;
};
