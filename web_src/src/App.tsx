import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardFooter,
  CardHeader,
  Caption1,
  Divider,
  MessageBar,
  MessageBarBody,
  MessageBarTitle,
  SearchBox,
  Skeleton,
  SkeletonItem,
  Spinner,
  Subtitle1,
  Text,
  Title1,
  Tooltip,
  makeStyles,
  mergeClasses,
  shorthands,
  tokens
} from "@fluentui/react-components";
import {
  ArrowClockwise20Regular,
  Circle20Filled,
  Dismiss20Regular,
  Pause20Filled,
  Play20Filled,
  RecordStop20Filled
} from "@fluentui/react-icons";
import { runtimeApi } from "./api";
import { t } from "./i18n";
import type { AutomationTask, EventRecord, ExecutorStatus, RuntimeEvent } from "./types";

const useStyles = makeStyles({
  shell: {
    minHeight: "100vh",
    backgroundColor: "#0b1118",
    color: tokens.colorNeutralForeground1
  },
  main: {
    width: "min(1180px, calc(100% - 32px))",
    margin: "0 auto",
    paddingTop: "40px",
    paddingBottom: "64px"
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "24px",
    marginBottom: "28px"
  },
  eyebrow: {
    color: tokens.colorBrandForeground1,
    letterSpacing: "0.16em",
    textTransform: "uppercase"
  },
  title: { display: "block", marginTop: "4px", letterSpacing: "-0.035em" },
  subtitle: { display: "block", color: tokens.colorNeutralForeground3, marginTop: "8px" },
  connection: { display: "flex", alignItems: "center", gap: "7px", marginTop: "8px" },
  connectionDot: { color: tokens.colorPaletteYellowForeground1, fontSize: "9px" },
  connectionDotLive: { color: tokens.colorPaletteGreenForeground1 },
  statusCard: {
    ...shorthands.border("1px", "solid", tokens.colorNeutralStroke2),
    backgroundColor: "#121b25",
    marginBottom: "32px"
  },
  statusGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(130px, 1fr)) auto",
    alignItems: "center",
    gap: "24px",
    padding: "22px"
  },
  metric: { display: "grid", gap: "4px" },
  muted: { color: tokens.colorNeutralForeground3 },
  actions: { display: "flex", justifyContent: "flex-end", flexWrap: "wrap", gap: "8px" },
  error: { marginBottom: "24px" },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "16px",
    marginBottom: "14px"
  },
  taskTools: { display: "flex", alignItems: "center", gap: "8px" },
  search: { width: "min(320px, 48vw)" },
  taskGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
    gap: "12px",
    marginBottom: "36px"
  },
  taskCard: {
    ...shorthands.border("1px", "solid", tokens.colorNeutralStroke2),
    backgroundColor: "#121b25",
    minHeight: "174px"
  },
  taskRunning: { ...shorthands.borderColor(tokens.colorBrandStroke1) },
  taskHeader: { minHeight: "74px" },
  taskMeta: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" },
  taskDescription: {
    color: tokens.colorNeutralForeground3,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden"
  },
  taskFooter: { justifyContent: "space-between", marginTop: "auto" },
  empty: { color: tokens.colorNeutralForeground3, padding: "32px 4px" },
  eventsCard: {
    ...shorthands.border("1px", "solid", tokens.colorNeutralStroke2),
    backgroundColor: "#121b25"
  },
  eventHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 20px" },
  eventList: { listStyleType: "none", margin: 0, padding: "0 20px 12px", maxHeight: "330px", overflowY: "auto" },
  eventRow: {
    display: "grid",
    gridTemplateColumns: "86px 150px minmax(0, 1fr)",
    gap: "12px",
    alignItems: "baseline",
    paddingTop: "10px",
    paddingBottom: "10px"
  },
  eventValue: { color: tokens.colorNeutralForeground3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  skeleton: { display: "grid", gap: "12px" },
  skeletonRow: { height: "174px" },
  mobile: {
    "@media (max-width: 720px)": {
      gridTemplateColumns: "1fr",
      alignItems: "stretch"
    }
  },
  mobileActions: {
    "@media (max-width: 720px)": { justifyContent: "stretch", "& > button": { flexGrow: 1 } }
  },
  mobileEvent: {
    "@media (max-width: 620px)": { gridTemplateColumns: "68px minmax(0, 1fr)", "& > :last-child": { gridColumnStart: 1, gridColumnEnd: 3 } }
  }
});

const refreshEvents = new Set(["task", "task_done", "executor_paused", "task_list_updated"]);

function stringify(value: unknown): string {
  if (typeof value === "string") return value;
  try { return JSON.stringify(value); } catch { return String(value); }
}

export default function App() {
  const styles = useStyles();
  const [status, setStatus] = useState<ExecutorStatus | null>(null);
  const [tasks, setTasks] = useState<AutomationTask[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [query, setQuery] = useState("");
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const eventId = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, nextTasks] = await Promise.all([runtimeApi.status(), runtimeApi.tasks()]);
      setStatus(nextStatus);
      setTasks(nextTasks);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("Could not reach the automation runtime"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let stopped = false;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/api/events`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = ({ data }) => {
        const message = JSON.parse(data) as RuntimeEvent;
        setEvents((current) => [{ ...message, id: ++eventId.current, timestamp: new Date() }, ...current].slice(0, 100));
        if (refreshEvents.has(message.event)) void refresh();
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) reconnectTimer = window.setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [refresh]);

  const perform = async (name: string, action: () => Promise<unknown>) => {
    setPending(name);
    try { await action(); await refresh(); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("Action failed")); }
    finally { setPending(null); }
  };

  const visibleTasks = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return tasks;
    return tasks.filter((task) => [task.name, task.class_name, task.description].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [query, tasks]);

  return (
    <div className={styles.shell}>
      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <Caption1 className={styles.eyebrow}>{t("Automation control")}</Caption1>
            <Title1 className={styles.title}>ok-script</Title1>
            <Text className={styles.subtitle}>{t("A local command center for tasks, triggers, and runtime events.")}</Text>
          </div>
          <div className={styles.connection} aria-live="polite">
            <Circle20Filled className={mergeClasses(styles.connectionDot, connected && styles.connectionDotLive)} />
            <Badge appearance="outline" color={connected ? "success" : "warning"}>{connected ? t("Live") : t("Reconnecting")}</Badge>
          </div>
        </header>

        {error && <MessageBar className={styles.error} intent="error"><MessageBarBody><MessageBarTitle>{t("Runtime error")}</MessageBarTitle>{error}</MessageBarBody></MessageBar>}

        <Card className={styles.statusCard}>
          <div className={mergeClasses(styles.statusGrid, styles.mobile)}>
            <div className={styles.metric}><Caption1 className={styles.muted}>{t("Executor")}</Caption1><Subtitle1>{status?.running ? (status.paused ? t("Paused") : t("Running")) : t("Idle")}</Subtitle1></div>
            <div className={styles.metric}><Caption1 className={styles.muted}>{t("Current task")}</Caption1><Subtitle1>{status?.current_task || t("None")}</Subtitle1></div>
            <div className={mergeClasses(styles.actions, styles.mobileActions)}>
              <Button icon={<Play20Filled />} appearance="primary" disabled={pending !== null} onClick={() => void perform("resume", runtimeApi.resume)}>{t("Resume")}</Button>
              <Button icon={<Pause20Filled />} disabled={pending !== null} onClick={() => void perform("pause", runtimeApi.pause)}>{t("Pause")}</Button>
              <Button icon={<RecordStop20Filled />} appearance="subtle" disabled={pending !== null || !status?.current_task} onClick={() => void perform("stop", runtimeApi.stopTask)}>{t("Stop task")}</Button>
            </div>
          </div>
        </Card>

        <section aria-labelledby="tasks-title">
          <div className={styles.sectionHeader}>
            <div><Subtitle1 id="tasks-title">{t("Tasks")}</Subtitle1><Caption1 className={styles.muted}> {t("{count} available", { count: status?.task_count ?? tasks.length })}</Caption1></div>
            <div className={styles.taskTools}>
              <SearchBox className={styles.search} aria-label={t("Filter tasks")} placeholder={t("Filter tasks")} value={query} onChange={(_, data) => setQuery(data.value)} />
              <Tooltip content={t("Refresh")} relationship="label"><Button aria-label={t("Refresh tasks")} icon={<ArrowClockwise20Regular />} onClick={() => void refresh()} /></Tooltip>
            </div>
          </div>
          {loading ? (
            <div className={styles.taskGrid}>{[0, 1, 2].map((item) => <Skeleton key={item} className={styles.skeleton}><SkeletonItem className={styles.skeletonRow} /></Skeleton>)}</div>
          ) : visibleTasks.length ? (
            <div className={styles.taskGrid}>
              {visibleTasks.map((task) => (
                <Card key={task.class_name} className={mergeClasses(styles.taskCard, task.running && styles.taskRunning)}>
                  <CardHeader className={styles.taskHeader} header={<Text weight="semibold">{task.name}</Text>} description={<Text className={styles.taskDescription}>{task.description || task.class_name}</Text>} />
                  <div className={styles.taskMeta}><Badge appearance="outline" color={task.trigger ? "brand" : "informative"}>{task.trigger ? t("Trigger") : t("One-time")}</Badge>{task.running && <Badge color="success">{t("Running")}</Badge>}{task.paused && <Badge color="warning">{t("Paused")}</Badge>}</div>
                  <CardFooter className={styles.taskFooter}><Caption1 className={styles.muted}>{task.class_name}</Caption1><Button appearance="primary" icon={pending === task.name ? <Spinner size="tiny" /> : <Play20Filled />} disabled={pending !== null || task.running} onClick={() => void perform(task.name, () => runtimeApi.startTask(task.name))}>{t("Start")}</Button></CardFooter>
                </Card>
              ))}
            </div>
          ) : <Text className={styles.empty}>{t("No tasks match “{query}”.", { query })}</Text>}
        </section>

        <Card className={styles.eventsCard}>
          <div className={styles.eventHeader}><div><Subtitle1>{t("Live events")}</Subtitle1><Caption1 className={styles.muted}> {t("Latest 100 messages")}</Caption1></div><Button appearance="subtle" icon={<Dismiss20Regular />} onClick={() => setEvents([])}>{t("Clear")}</Button></div>
          <Divider />
          <ol className={styles.eventList} aria-live="polite">
            {events.length ? events.map((event) => <li key={event.id} className={mergeClasses(styles.eventRow, styles.mobileEvent)}><Caption1 className={styles.muted}>{event.timestamp.toLocaleTimeString()}</Caption1><Text weight="semibold">{event.event}</Text><Caption1 className={styles.eventValue} title={stringify(event.args)}>{stringify(event.args)}</Caption1></li>) : <li className={styles.eventRow}><Caption1 className={styles.muted}>{t("Waiting for runtime events…")}</Caption1></li>}
          </ol>
        </Card>
      </main>
    </div>
  );
}
