export type ExecutorStatus = {
  paused: boolean;
  running: boolean;
  current_task: string | null;
  task_count: number;
};

export type AutomationTask = {
  name: string;
  class_name: string;
  enabled: boolean;
  running: boolean;
  paused: boolean;
  trigger: boolean;
  description: string;
};

export type RuntimeEvent = {
  event: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
};

export type EventRecord = RuntimeEvent & {
  id: number;
  timestamp: Date;
};
