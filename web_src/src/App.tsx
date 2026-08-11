import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert20Regular,
  ArrowClockwise20Regular,
  Calendar20Regular,
  Camera20Regular,
  CheckmarkCircle20Regular,
  Code20Regular,
  DeveloperBoard20Regular,
  Dismiss20Regular,
  DocumentText20Regular,
  Edit20Regular,
  ErrorCircle20Regular,
  Folder20Regular,
  Games20Regular,
  Image20Regular,
  Info20Regular,
  Navigation20Regular,
  People20Regular,
  Play20Regular,
  QuestionCircle20Regular,
  Search20Regular,
  Settings20Regular,
  TaskListSquareLtr20Regular,
  Timer20Regular,
  Pause20Regular,
  WeatherMoon20Regular,
  Window20Regular
} from "@fluentui/react-icons";
import { runtimeApi } from "./api";
import { t } from "./i18n";
import type { CaptureUiState, LogResponse, MethodOption } from "./types";

type IconComponent = typeof Play20Regular;
type Notice = { message: string; intent: "success" | "info" };

const primaryNavigation: Array<[string, IconComponent]> = [
  ["Capture", Play20Regular],
  ["Triggers", Timer20Regular],
  ["Tasks", TaskListSquareLtr20Regular],
  ["Character Code", Code20Regular],
  ["Script", Edit20Regular],
  ["Templates", Image20Regular],
  ["Schedule", Calendar20Regular],
  ["Character Settings", People20Regular],
  ["Game Hotkeys", Games20Regular]
];

const secondaryNavigation: Array<[string, IconComponent]> = [
  ["Notifications", Alert20Regular],
  ["Settings", Settings20Regular],
  ["About", QuestionCircle20Regular]
];

// Most runtime events (box drawing, screenshots, progress, logs) do not alter
// StartTab controls. Refreshing for every event can produce hundreds of HTTP
// requests per second while automation is active.
const captureStateEvents = new Set([
  "adb_devices",
  "executor_paused",
  "starting_emulator",
  "task",
  "task_list_updated"
]);

function MethodList({ items, onSelect, disabled }: {
  items: MethodOption[];
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  return <div className="option-list" role="listbox">
    {items.map((item) => <button
      type="button"
      role="option"
      aria-selected={item.selected}
      className={`option-row ${item.selected ? "selected" : ""}`}
      disabled={disabled}
      key={item.id}
      onClick={() => onSelect(item.id)}
    >{item.label}</button>)}
    {!items.length && <div className="empty-option">{t("No options available")}</div>}
  </div>;
}

function Switch({ checked, label, disabled, onChange }: {
  checked: boolean;
  label: string;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return <label className="switch-control">
    <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
    <span className="switch-track"><span className="switch-thumb" /></span>
    <span>{label}</span>
  </label>;
}

export default function App() {
  useEffect(() => {
    const updateDesktopScale = () => {
      // Edge can expose a several-thousand-pixel CSS viewport in desktop mode
      // when browser/display scaling is reduced. Scale the complete desktop UI
      // against the layout's reference viewport so controls remain usable.
      const widthScale = window.innerWidth / 1536;
      const heightScale = window.innerHeight / 864;
      const scale = Math.min(5, Math.max(1.25, Math.min(widthScale, heightScale)));
      document.documentElement.style.setProperty("--desktop-scale", scale.toFixed(3));
    };

    updateDesktopScale();
    window.addEventListener("resize", updateDesktopScale);
    window.visualViewport?.addEventListener("resize", updateDesktopScale);
    return () => {
      window.removeEventListener("resize", updateDesktopScale);
      window.visualViewport?.removeEventListener("resize", updateDesktopScale);
      document.documentElement.style.removeProperty("--desktop-scale");
    };
  }, []);

  const [ui, setUi] = useState<CaptureUiState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [captureUrl, setCaptureUrl] = useState<string | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsPaused, setLogsPaused] = useState(false);
  const [logLevel, setLogLevel] = useState("ALL");
  const [logQuery, setLogQuery] = useState("");
  const [logData, setLogData] = useState<LogResponse | null>(null);
  const logConsole = useRef<HTMLPreElement>(null);

  const load = useCallback(async () => {
    try {
      setUi(await runtimeApi.captureUi());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("Could not reach the automation runtime"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!logsOpen || logsPaused) return;
    let stopped = false;
    let timer: number | undefined;
    const refreshLogs = async () => {
      try {
        const data = await runtimeApi.logs(logLevel, logQuery);
        if (!stopped) setLogData(data);
      } catch (reason) {
        if (!stopped) setError(reason instanceof Error ? reason.message : t("Could not load logs"));
      } finally {
        if (!stopped) timer = window.setTimeout(refreshLogs, 750);
      }
    };
    void refreshLogs();
    return () => { stopped = true; if (timer) clearTimeout(timer); };
  }, [logLevel, logQuery, logsOpen, logsPaused]);

  useEffect(() => {
    const consoleElement = logConsole.current;
    if (consoleElement && !logsPaused) consoleElement.scrollTop = consoleElement.scrollHeight;
  }, [logData, logsPaused]);

  useEffect(() => {
    const closeModal = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setCaptureUrl(null); setLogsOpen(false); }
    };
    window.addEventListener("keydown", closeModal);
    return () => window.removeEventListener("keydown", closeModal);
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let stopped = false;
    const connect = () => {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${location.host}/api/events`);
      socket.onmessage = ({ data }) => {
        let event: { event?: string; ui?: CaptureUiState };
        try { event = JSON.parse(data) as { event?: string; ui?: CaptureUiState }; }
        catch { return; }
        if (!event.event || !captureStateEvents.has(event.event)) return;
        // The server attaches the new UI state for relevant events. Do not
        // follow every event with another HTTP request.
        if (event.ui) setUi(event.ui);
        if (event.event === "adb_devices") setPending((current) => current === "refresh" ? null : current);
      };
      socket.onclose = () => { if (!stopped) timer = window.setTimeout(connect, 1500); };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [load]);

  const perform = async (name: string, action: () => Promise<CaptureUiState>) => {
    setPending(name);
    try { setUi(await action()); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("Action failed")); }
    finally { setPending(null); }
  };

  const tool = async (name: string) => {
    setPending(name);
    try {
      const result = await runtimeApi.tool(name);
      setNotice({ message: result.message, intent: "success" });
      if (result.kind === "capture" && result.resource_url) setCaptureUrl(result.resource_url);
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("Action failed")); }
    finally { setPending(null); }
  };

  const refreshDevices = async () => {
    setPending("refresh");
    try {
      await runtimeApi.refreshDevices();
      setError(null);
      // Completion and the updated device list arrive through adb_devices.
    } catch (reason) {
      setPending(null);
      setError(reason instanceof Error ? reason.message : t("Action failed"));
    }
  };

  const devices = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return (ui?.devices ?? []).filter((device) => !normalized || `${device.label} ${device.keywords}`.toLocaleLowerCase().includes(normalized));
  }, [query, ui?.devices]);

  const status = ui?.status;
  const startLabel = status?.paused === false ? t("Pause") : `${t("Start")}${status?.hotkey ? `(${status.hotkey})` : ""}`;
  const StartStateIcon = status?.paused === false ? Pause20Regular : Play20Regular;

  return <div className={`desktop ${collapsed ? "nav-collapsed" : ""}`}>
    <aside className="sidebar">
      <button type="button" className="nav-toggle" aria-label={t("Toggle navigation")} onClick={() => setCollapsed((value) => !value)}><Navigation20Regular /></button>
      <nav className="nav-primary">
        {primaryNavigation.map(([label, Icon], index) => <button
          type="button"
          key={label}
          className={`nav-item ${index === 0 ? "active" : ""}`}
          title={t(label)}
          onClick={() => index !== 0 && setNotice({ message: t("{page} is not available in the web UI yet.", { page: t(label) }), intent: "info" })}
        ><Icon /><span>{t(label)}</span></button>)}
      </nav>
      <nav className="nav-secondary">
        {secondaryNavigation.map(([label, Icon]) => <button type="button" key={label} className="nav-item" title={t(label)} onClick={() => setNotice({ message: t("{page} is not available in the web UI yet.", { page: t(label) }), intent: "info" })}><Icon /><span>{t(label)}</span></button>)}
      </nav>
    </aside>

    <div className="toast-stack" aria-live="polite">
      {error && <div className="toast toast-error" role="alert"><ErrorCircle20Regular /><span>{error}</span><button type="button" aria-label={t("Close")} onClick={() => setError(null)}><Dismiss20Regular /></button></div>}
      {notice && <div className={`toast toast-${notice.intent}`} role="status">{notice.intent === "success" ? <CheckmarkCircle20Regular /> : <Info20Regular />}<span>{notice.message}</span><button type="button" aria-label={t("Close")} onClick={() => setNotice(null)}><Dismiss20Regular /></button></div>}
    </div>

    <main className="content">
      <section className="start-card surface-card">
        <div className="app-identity"><div className="app-avatar">{ui?.icon_url ? <img src={ui.icon_url} alt="" /> : "OK"}</div><div><strong>{ui?.title || "OK-WW"}</strong><small>{ui?.version || "dev"}</small></div></div>
        <div className="start-actions">
          <button type="button" disabled={pending !== null} onClick={() => void tool("capture")}><Camera20Regular />{t("Capture")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void refreshDevices()}><ArrowClockwise20Regular />{pending === "refresh" ? t("Refreshing") : t("Refresh")}</button>
          <button className="primary-button" type="button" disabled={pending !== null || loading} onClick={() => void perform("start", status?.paused === false ? async () => { await runtimeApi.pause(); return runtimeApi.captureUi(); } : async () => { await runtimeApi.resume(); return runtimeApi.captureUi(); })}><StartStateIcon />{startLabel}</button>
        </div>
      </section>

      <section className="selectors">
        <div className="selector-column window-column">
          <h2>{t("Choose Window")}</h2>
          <div className="surface-card selector-card">
            <label className="device-search"><Search20Regular /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search title or exe...")} /></label>
            <div className="option-list" role="listbox">
              {devices.map((device) => <button
                type="button"
                role="option"
                aria-selected={device.selected}
                className={`option-row ${device.selected ? "selected" : ""}`}
                disabled={pending !== null}
                key={device.id}
                onClick={() => void perform("device", () => runtimeApi.selectDevice(device.id))}
              ><span>{device.label}</span>{!device.connected && <small>{t("Disconnected")}</small>}</button>)}
              {!devices.length && <div className="empty-option">{loading ? t("Loading") : t("No windows found")}</div>}
            </div>
          </div>
        </div>
        <div className="selector-column">
          <h2>{t("Capture Method")}</h2>
          <div className="surface-card selector-card"><MethodList items={ui?.capture_methods ?? []} disabled={pending !== null} onSelect={(id) => void perform("capture-method", () => runtimeApi.selectCapture(id))} /></div>
        </div>
        <div className="selector-column">
          <h2>{t("Choose Interaction")}</h2>
          <div className="surface-card selector-card"><MethodList items={ui?.interaction_methods ?? []} disabled={pending !== null} onSelect={(id) => void perform("interaction-method", () => runtimeApi.selectInteraction(id))} /></div>
        </div>
      </section>

      <section className="page-section">
        <h2>{t("Debug")}</h2>
        <div className="surface-card tool-card">
          <button type="button" disabled={pending !== null} onClick={() => void tool("export-logs")}><DocumentText20Regular />{t("Export Logs")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void tool("install-folder")}><Folder20Regular />{t("Install Folder")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void tool("screenshot-folder")}><Folder20Regular />{t("Screenshot Folder")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void tool("log-folder")}><Folder20Regular />{t("Log Folder")}</button>
          <button type="button" disabled={pending !== null} onClick={() => setLogsOpen(true)}><DeveloperBoard20Regular />{t("View Log")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void tool("ocr")}><Search20Regular />OCR</button>
        </div>
      </section>

      <section className="page-section overlay-section">
        <h2>{t("Debug Overlay")}</h2>
        <div className="surface-card switch-card">
          <Switch checked={ui?.overlay.boxes ?? false} disabled={pending !== null || !ui} label={(ui?.overlay.boxes ?? false) ? t("Enable Boxes") : t("Disable Boxes")} onChange={(value) => void perform("overlay", () => runtimeApi.setOverlay("boxes", value))} />
          <Switch checked={ui?.overlay.logs ?? false} disabled={pending !== null || !ui} label={(ui?.overlay.logs ?? false) ? t("Show Log on Overlay") : t("Hide Log on Overlay")} onChange={(value) => void perform("overlay", () => runtimeApi.setOverlay("logs", value))} />
        </div>
      </section>
      <div className="content-spacer" />
    </main>
    {captureUrl && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setCaptureUrl(null)}>
      <section className="modal capture-modal" role="dialog" aria-modal="true" aria-label={t("Capture Preview")}>
        <header><strong>{t("Capture Preview")}</strong><div className="modal-header-actions"><button className="modal-text-button" type="button" onClick={() => void tool("screenshot-folder")}><Folder20Regular />{t("Open Screenshot Folder")}</button><button type="button" aria-label={t("Close")} onClick={() => setCaptureUrl(null)}><Dismiss20Regular /></button></div></header>
        <div className="capture-preview"><img src={captureUrl} alt={t("Captured game frame")} /></div>
      </section>
    </div>}
    {logsOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setLogsOpen(false)}>
      <section className="modal log-modal" role="dialog" aria-modal="true" aria-label={t("View Log")}>
        <header><strong>{t("View Log")}</strong><button type="button" aria-label={t("Close")} onClick={() => setLogsOpen(false)}><Dismiss20Regular /></button></header>
        <div className="log-toolbar">
          <select aria-label={t("Log level")} value={logLevel} onChange={(event) => setLogLevel(event.target.value)}>
            <option value="ALL">{t("All Levels")}</option><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option><option>CRITICAL</option>
          </select>
          <label><Search20Regular /><input value={logQuery} onChange={(event) => setLogQuery(event.target.value)} placeholder={t("Filter logs...")} /></label>
          <button type="button" onClick={() => setLogsPaused((value) => !value)}>{logsPaused ? <Play20Regular /> : <Pause20Regular />}{logsPaused ? t("Resume") : t("Pause")}</button>
          <button type="button" onClick={() => { setLogsPaused(true); setLogData((current) => current ? { ...current, text: "", line_count: 0 } : current); }}><Dismiss20Regular />{t("Clear")}</button>
        </div>
        <pre ref={logConsole} className="log-console">{logData?.text || t("Waiting for ok-script.log")}</pre>
        <footer>{logData?.path || "logs/ok-script.log"} · {logData?.line_count ?? 0} {t("lines")}</footer>
      </section>
    </div>}
    <div className="theme-mark"><WeatherMoon20Regular /><Window20Regular /></div>
  </div>;
}
