import { useEffect, useRef, useState } from "react";
import { runtimeApi } from "./api";
import { locale, t } from "./i18n";
import type { AutomationTask, TaskTabEvent, TaskTabManifest } from "./types";

type Notify = (message: string, intent: "success" | "info" | "error") => void;

type TaskTabContext = {
  tab: TaskTabManifest;
  query: <T>(name: string, input?: Record<string, unknown>) => Promise<T>;
  action: <T>(name: string, input?: Record<string, unknown>) => Promise<T>;
  task: {
    getState: () => Promise<AutomationTask>;
    start: () => Promise<AutomationTask>;
    pause: () => Promise<AutomationTask>;
    resume: () => Promise<AutomationTask>;
    stop: () => Promise<AutomationTask>;
    setConfig: (key: string, value: unknown) => Promise<AutomationTask>;
  };
  subscribe: (handler: (event: TaskTabEvent) => void) => () => void;
  notify: Notify;
  t: typeof t;
  locale: string;
  theme: "light" | "dark";
  setDirty: (dirty: boolean) => void;
  registerSave: (save: (() => Promise<boolean>) | null) => void;
};

type TaskTabModule = {
  mount: (container: HTMLElement, context: TaskTabContext) => void | (() => void);
};

const EVENT_NAME = "ok-task-tab-event";

export function TaskTabHost({ tab, notify, onDirtyChange, registerSave }: {
  tab: TaskTabManifest;
  notify: Notify;
  onDirtyChange: (dirty: boolean) => void;
  registerSave: (save: (() => Promise<boolean>) | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let active = true;
    let unmount: (() => void) | undefined;

    const getState = async () => {
      const task = (await runtimeApi.tasks()).find(
        (candidate) => candidate.class_name === tab.task_class_name
      );
      if (!task) throw new Error(`Task is no longer registered: ${tab.task_class_name}`);
      return task;
    };
    const act = async (action: "pause" | "resume" | "stop") =>
      runtimeApi.taskAction(tab.task_name, action);

    const context: TaskTabContext = {
      tab,
      query: (name, input = {}) => runtimeApi.taskTabQuery(tab.id, name, input),
      action: (name, input = {}) => runtimeApi.taskTabAction(tab.id, name, input),
      task: {
        getState,
        start: () => runtimeApi.startTask(tab.task_name),
        pause: () => act("pause"),
        resume: () => act("resume"),
        stop: async () => {
          const state = await getState();
          return state.trigger
            ? runtimeApi.taskAction(tab.task_name, "disable")
            : act("stop");
        },
        setConfig: (key, value) => runtimeApi.setTaskConfig(tab.task_name, key, value)
      },
      subscribe: (handler) => {
        const listener = (event: Event) => {
          const detail = (event as CustomEvent<TaskTabEvent>).detail;
          if (detail?.tab_id === tab.id) handler(detail);
        };
        window.addEventListener(EVENT_NAME, listener);
        return () => window.removeEventListener(EVENT_NAME, listener);
      },
      notify,
      t,
      locale,
      theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
      setDirty: onDirtyChange,
      registerSave
    };

    void import(/* @vite-ignore */ tab.module_url).then((module: TaskTabModule) => {
      if (!active) return;
      if (typeof module.mount !== "function") {
        throw new Error(`Task tab module does not export mount(): ${tab.module_url}`);
      }
      const cleanup = module.mount(container, context);
      if (typeof cleanup === "function") unmount = cleanup;
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    });

    return () => {
      active = false;
      unmount?.();
      registerSave(null);
      onDirtyChange(false);
      container.replaceChildren();
    };
  }, [notify, onDirtyChange, registerSave, tab]);

  if (error) return <div className="task-empty" role="alert">{t("Could not load custom tab")}: {error}</div>;
  return <div ref={containerRef} className="task-tab-host" />;
}

export function publishTaskTabEvent(event: TaskTabEvent) {
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: event }));
}
