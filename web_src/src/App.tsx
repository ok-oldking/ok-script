import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { Button, Dropdown, FluentProvider, Input, Menu, MenuDivider, MenuItem, MenuList, MenuPopover, MenuTrigger, Option, SpinButton, webDarkTheme, webLightTheme } from "@fluentui/react-components";
import {
  Alert20Regular,
  Add20Regular,
  ArrowDown20Regular,
  ArrowExport20Regular,
  ArrowImport20Regular,
  ArrowClockwise20Regular,
  ArrowUp20Regular,
  Calendar20Regular,
  Camera20Regular,
  CheckmarkCircle20Regular,
  ChevronDown20Regular,
  Copy20Regular,
  DeveloperBoard20Regular,
  Delete20Regular,
  Dismiss20Regular,
  DocumentText20Regular,
  Edit20Regular,
  ErrorCircle20Regular,
  Folder20Regular,
  Globe20Regular,
  Image20Regular,
  Info20Regular,
  LocalLanguage20Regular,
  Navigation20Regular,
  PaintBrush20Regular,
  Play20Regular,
  QuestionCircle20Regular,
  Record20Regular,
  Search20Regular,
  Save20Regular,
  Settings20Regular,
  Square20Regular,
  Stop20Regular,
  Subtract20Regular,
  TaskListSquareLtr20Regular,
  Timer20Regular,
  Pause20Regular,
  WeatherMoon20Regular,
  Window20Regular
} from "@fluentui/react-icons";
import { runtimeApi } from "./api";
import { ConfirmDeleteDialog } from "./ConfirmDialog";
import { locale, setLocale, t } from "./i18n";
import { MarkupDialog } from "./MarkupDialog";
import { PythonCodeEditor } from "./PythonCodeEditor";
import { CreateScriptDialog, ExportScriptDialog, ExternalScriptChangeDialog, ImportScriptDialog, RecordScriptDialog, TemplateParameterDialog, UnsavedScriptDialog } from "./ScriptDialogs";
import { publishTaskTabEvent, TaskTabHost } from "./TaskTabHost";
import type { AboutInfo, AutomationTask, CaptureUiState, LogResponse, MethodOption, NavigationCapabilities, RuntimeEvent, ScheduleData, ScheduledTask, ScriptDocument, ScriptSummary, ScriptTemplate, SettingsGroup, TaskConfigField, TemplateAnnotations, TemplateImage, UpdateCheckResult } from "./types";

type IconComponent = typeof Play20Regular;
type ToastMessage = { id: number; message: string; intent: "success" | "info" | "error" };
type AppTheme = "Light" | "Dark" | "Auto";
type SystemAccent = { light: string; dark: string };

type PywebviewWindowApi = {
  minimize: () => Promise<void>;
  toggle_maximize: () => Promise<boolean>;
  close: () => Promise<void>;
};

declare global {
  interface Window {
    pywebview?: { api?: PywebviewWindowApi };
  }
}

const WINDOWS_STANDARD_BLUE = "#60cdff";
const SYSTEM_NOTIFICATION_KEY = "System Notification";
const PYWEBVIEW_LAUNCH = new URLSearchParams(window.location.search).get("pywebview") === "1";

function requestBrowserNotificationPermission() {
  if (!("Notification" in window)) return Promise.resolve("denied" as NotificationPermission);
  if (Notification.permission !== "default") {
    return Promise.resolve(Notification.permission);
  }
  return Notification.requestPermission();
}

function showBrowserNotification(title: string, message: string, iconUrl?: string | null) {
  if (!("Notification" in window) || Notification.permission !== "granted") return false;
  new Notification(title, { body: message, icon: iconUrl || undefined });
  return true;
}

function formatEventText(message: string, params: unknown) {
  if (!params || typeof params !== "object") return message;
  return Object.entries(params as Record<string, unknown>).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)), message
  );
}

const languageOptions = [
  ["zh_CN", "简体中文"], ["zh_TW", "繁體中文"], ["en_US", "English"],
  ["es_ES", "Español"], ["ja_JP", "日本語"], ["ko_KR", "한국인"], ["Auto", "Use system setting"]
] as const;

function mixHex(source: string, target: string, amount: number) {
  const parse = (value: string) => [1, 3, 5].map((index) => Number.parseInt(value.slice(index, index + 2), 16));
  const from = parse(source);
  const to = parse(target);
  return `#${from.map((channel, index) => Math.round(channel + (to[index] - channel) * amount).toString(16).padStart(2, "0")).join("")}`;
}

const themed = (base: typeof webDarkTheme, dark: boolean, accent: string) => ({
  ...base,
  colorBrandBackground: accent,
  colorBrandBackgroundHover: mixHex(accent, "#ffffff", 0.14),
  colorBrandBackgroundPressed: mixHex(accent, "#000000", 0.12),
  colorBrandBackgroundSelected: accent,
  colorBrandForeground1: dark ? accent : mixHex(accent, "#000000", 0.38),
  colorBrandForeground2: dark ? mixHex(accent, "#ffffff", 0.14) : mixHex(accent, "#000000", 0.48),
  colorBrandStroke1: accent,
  colorBrandStroke2: accent,
  colorCompoundBrandForeground1: dark ? accent : mixHex(accent, "#000000", 0.38),
  colorCompoundBrandForeground1Hover: dark ? mixHex(accent, "#ffffff", 0.14) : mixHex(accent, "#000000", 0.48),
  colorCompoundBrandStroke: accent,
  colorCompoundBrandStrokeHover: mixHex(accent, "#000000", 0.12),
  colorNeutralForegroundOnBrand: "#102a35"
});

const primaryNavigation: Array<[string, IconComponent]> = [
  ["Capture", Play20Regular]
];

const secondaryNavigation: Array<[string, IconComponent]> = [
  ["Notifications", Alert20Regular],
  ["Settings", Settings20Regular],
  ["About", QuestionCircle20Regular]
];

const opticallyHighNavigationIcons = new Set(["Capture", "Triggers"]);

function taskTabIcon(icon: string): IconComponent {
  if (icon === "settings") return Settings20Regular;
  if (icon === "image") return Image20Regular;
  if (icon === "calendar") return Calendar20Regular;
  if (icon === "play") return Play20Regular;
  return DeveloperBoard20Regular;
}

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

const taskStateEvents = new Set(["task", "task_done", "executor_paused", "task_list_updated"]);

function MethodList({ items, label, onSelect, disabled }: {
  items: MethodOption[];
  label: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  return <div className="option-list" role="group" aria-label={label}>
    {items.map((item) => <button
      type="button"
      aria-pressed={item.selected}
      className={`option-row ${item.selected ? "selected" : ""}`}
      disabled={disabled}
      key={item.id}
      onClick={() => onSelect(item.id)}
    >{item.label}</button>)}
    {!items.length && <div className="empty-option">{t("No options available")}</div>}
  </div>;
}

function useDialogFocus(open: boolean, dialogRef: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusableSelector = [
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[href]",
      "[tabindex]:not([tabindex='-1'])"
    ].join(",");
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
    (dialog.querySelector<HTMLElement>("[data-autofocus]") ?? focusable()[0] ?? dialog).focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const elements = focusable();
      if (!elements.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [dialogRef, onClose, open]);
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

function ListConfigControl({ field, disabled, onCommit }: {
  field: TaskConfigField;
  disabled: boolean;
  onCommit: (value: unknown[]) => void;
}) {
  const current = Array.isArray(field.value) ? field.value : [];
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<unknown[]>(current);
  const [selected, setSelected] = useState<number | null>(null);
  const [newItem, setNewItem] = useState("");
  const display = current.map(String).join(", ");

  const beginEdit = () => {
    setItems([...current]);
    setSelected(null);
    setNewItem("");
    setOpen(true);
  };
  const add = (value: unknown) => {
    if (!field.allow_duplication && items.some((item) => JSON.stringify(item) === JSON.stringify(value))) return;
    setItems((existing) => [...existing, value]);
    setSelected(items.length);
  };
  const move = (direction: -1 | 1) => {
    if (selected === null) return;
    const destination = selected + direction;
    if (destination < 0 || destination >= items.length) return;
    setItems((existing) => {
      const next = [...existing];
      [next[selected], next[destination]] = [next[destination], next[selected]];
      return next;
    });
    setSelected(destination);
  };
  const remove = () => {
    if (selected === null) return;
    setItems((existing) => existing.filter((_item, index) => index !== selected));
    setSelected((index) => index === null || items.length <= 1 ? null : Math.min(index, items.length - 2));
  };

  return <>
    <div className="task-config-control list-summary"><span title={display}>{display || t("None")}</span><button type="button" disabled={disabled} onClick={beginEdit}><Edit20Regular /><span className="button-label">{t("Modify")}</span></button></div>
    {open && <div className="modal-backdrop list-editor-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
      <section className="modal list-editor-modal" role="dialog" aria-modal="true" aria-label={field.key}>
        <header><strong>{field.key}</strong><button type="button" aria-label={t("Close")} onClick={() => setOpen(false)}><Dismiss20Regular /></button></header>
        <div className="list-editor-content">
          {field.options ? <section><h2>{t("Available Options")}</h2><div className="available-list-options">{field.options.map((option, index) => {
            const alreadySelected = !field.allow_duplication && items.some((item) => JSON.stringify(item) === JSON.stringify(option));
            return <button type="button" key={index} disabled={alreadySelected} onClick={() => add(option)}><Add20Regular />{String(option)}</button>;
          })}</div></section> : <section><h2>{t("Add")}</h2><div className="list-add-row"><Input aria-label={t("Add")} value={newItem} onChange={(event) => setNewItem(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && newItem.trim()) { add(newItem.trim()); setNewItem(""); }
          }} /><button type="button" disabled={!newItem.trim()} onClick={() => { add(newItem.trim()); setNewItem(""); }}><Add20Regular />{t("Add")}</button></div></section>}
          <section className="selected-list-section"><h2>{t("Selected Options")}</h2><div className="selected-list-body"><ol>{items.map((item, index) => <li key={`${JSON.stringify(item)}-${index}`}><button type="button" className={selected === index ? "selected" : ""} onClick={() => setSelected(index)}>{String(item)}</button></li>)}</ol><div className="list-editor-actions">
            <button type="button" disabled={selected === null || selected === 0} onClick={() => move(-1)}><ArrowUp20Regular />{t("Move Up")}</button>
            <button type="button" disabled={selected === null || selected === items.length - 1} onClick={() => move(1)}><ArrowDown20Regular />{t("Move Down")}</button>
            <button type="button" disabled={selected === null} onClick={remove}><Delete20Regular />{t("Remove")}</button>
          </div></div></section>
        </div>
        <footer className="list-editor-footer"><button type="button" onClick={() => setOpen(false)}>{t("Cancel")}</button><button type="button" className="primary-button" onClick={() => { onCommit(items); setOpen(false); }}>{t("Confirm")}</button></footer>
      </section>
    </div>}
  </>;
}

function TaskConfigControl({ field, disabled, onCommit }: {
  field: TaskConfigField;
  disabled: boolean;
  onCommit: (value: unknown) => void;
}) {
  const [draft, setDraft] = useState(() => field.kind === "list"
    ? JSON.stringify(field.value, null, 2)
    : String(field.value ?? ""));

  useEffect(() => {
    setDraft(field.kind === "list" ? JSON.stringify(field.value, null, 2) : String(field.value ?? ""));
  }, [field.kind, field.value]);

  if (field.kind === "boolean") {
    return <div className="task-config-control boolean"><Switch checked={Boolean(field.value)} disabled={disabled} label={Boolean(field.value) ? t("Enabled") : t("Disabled")} onChange={onCommit} /></div>;
  }
  if (field.kind === "select") {
    const longestOption = Math.max(
      String(field.value ?? "").length,
      ...(field.options ?? []).map((option) => String(option).length)
    );
    const optionWidth = Math.min(36, Math.max(12, longestOption + 4));
    return <div className="task-config-control select"><Dropdown
      aria-label={field.key}
      disabled={disabled}
      inlinePopup
      style={{ width: `${optionWidth}ch` }}
      value={String(field.value ?? "")}
      selectedOptions={[JSON.stringify(field.value)]}
      onOptionSelect={(_event, data) => data.optionValue !== undefined && onCommit(JSON.parse(data.optionValue))}
    >{(field.options ?? []).map((option, index) => <Option className="task-config-option" key={index} value={JSON.stringify(option)} text={String(option)}>{String(option)}</Option>)}</Dropdown></div>;
  }
  if (field.kind === "multi_selection") {
    const values = Array.isArray(field.value) ? field.value : [];
    return <div className="task-config-options">{(field.options ?? []).map((option, index) => {
      const selected = values.some((value) => JSON.stringify(value) === JSON.stringify(option));
      return <label className="config-checkbox task-config-checkbox" key={index}>
        <input
          type="checkbox"
          disabled={disabled}
          checked={selected}
          onChange={(event) => onCommit(event.currentTarget.checked ? [...values, option] : values.filter((value) => JSON.stringify(value) !== JSON.stringify(option)))}
        />
        <svg className="config-checkbox-mark" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
          <rect x="1" y="1" width="18" height="18" rx="3" />
          <path d="M5.25 10.25 8.6 13.6 14.9 6.9" />
        </svg>
        <span className="config-checkbox-label">{String(option)}</span>
      </label>;
    })}</div>;
  }
  if (field.kind === "list") {
    return <ListConfigControl field={field} disabled={disabled} onCommit={onCommit} />;
  }
  if (field.kind === "multiline") {
    return <div className="task-config-control multiline"><textarea aria-label={field.key} disabled={disabled} value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={() => onCommit(draft)} /></div>;
  }
  const numeric = field.kind === "integer" || field.kind === "number";
  if (numeric) {
    return <div className="task-config-control number"><SpinButton
      aria-label={field.key}
      disabled={disabled}
      min={field.minimum ?? undefined}
      max={field.maximum ?? undefined}
      step={field.kind === "integer" ? 1 : 0.1}
      value={Number(draft)}
      onChange={(_event, data) => {
        if (data.value !== undefined) {
          setDraft(String(data.value));
          onCommit(data.value);
        }
      }}
    /></div>;
  }
  return <div className={`task-config-control text ${field.kind === "file" ? "file" : ""}`}><Input aria-label={field.key} disabled={disabled} value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={() => onCommit(draft)} /></div>;
}

function SettingsPage({ groups, loading, pending, theme, language, onTheme, onLanguage, onUpdate, onReset }: {
  groups: SettingsGroup[];
  loading: boolean;
  pending: string | null;
  theme: AppTheme;
  language: string;
  onTheme: (theme: AppTheme) => void;
  onLanguage: (language: string) => void;
  onUpdate: (group: SettingsGroup, field: TaskConfigField, value: unknown) => void;
  onReset: (group: SettingsGroup) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpanded((current) => {
      const next = new Set(current);
      groups.filter((group) => group.expanded).forEach((group) => next.add(group.name));
      return next;
    });
  }, [groups]);

  const busy = pending !== null;
  return <section className="settings-page" aria-label={t("Settings")}>
    <h1>{t("Settings")}</h1>
    <section className="settings-group">
      <h2>{t("App Config")}</h2>
      <div className="surface-card app-settings-card">
        <div className="task-config-row">
          <span><strong>{t("Application Theme")}</strong><small>{t("Change the appearance of the application")}</small></span>
          <div className="setting-control-with-icon"><PaintBrush20Regular /><Dropdown aria-label={t("Application Theme")} inlinePopup value={t(theme === "Auto" ? "Use system setting" : theme)} selectedOptions={[theme]} onOptionSelect={(_event, data) => data.optionValue && onTheme(data.optionValue as AppTheme)}>
            <Option value="Light">{t("Light")}</Option><Option value="Dark">{t("Dark")}</Option><Option value="Auto">{t("Use system setting")}</Option>
          </Dropdown></div>
        </div>
        <div className="task-config-row">
          <span><strong>{t("Language")}</strong><small>{t("Set your preferred language")}</small></span>
          <div className="setting-control-with-icon"><LocalLanguage20Regular /><Dropdown aria-label={t("Language")} inlinePopup value={languageOptions.find(([value]) => value === language)?.[1] ?? t("Use system setting")} selectedOptions={[language]} onOptionSelect={(_event, data) => data.optionValue && onLanguage(data.optionValue)}>
            {languageOptions.map(([value, label]) => <Option key={value} value={value}>{value === "Auto" ? t(label) : label}</Option>)}
          </Dropdown></div>
        </div>
      </div>
    </section>
    {loading && !groups.length ? <div className="task-empty">{t("Loading")}</div> : <div className="settings-groups">
      {groups.filter((group) => !group.top_level).map((group) => {
        const open = expanded.has(group.name);
        return <article key={group.name} className={`qt-task-card settings-config-card surface-card ${open ? "expanded" : ""}`}>
          <div className="qt-task-header"><button type="button" className="task-expand" aria-expanded={open} onClick={() => setExpanded((current) => {
            const next = new Set(current); if (next.has(group.name)) next.delete(group.name); else next.add(group.name); return next;
          })}><span><strong>{t(group.name)}</strong><small>{t(group.description)}</small></span><ChevronDown20Regular /></button></div>
          {open && <div className="task-config">
            {group.fields.map((field) => <div className={`task-config-row ${field.sub_config ? "sub-config" : ""}`} key={field.key}>
              <span><strong>{t(field.key)}</strong>{field.description && <small>{t(field.description)}</small>}</span>
              <TaskConfigControl field={field} disabled={busy} onCommit={(value) => {
                if (JSON.stringify(value) !== JSON.stringify(field.value)) onUpdate(group, field, value);
              }} />
            </div>)}
            <footer><button type="button" disabled={busy} onClick={() => onReset(group)}><span className="button-label">{t("Reset Config")}</span></button></footer>
          </div>}
        </article>;
      })}
    </div>}
  </section>;
}

function TopLevelSettingsPage({ group, loading, pending, onUpdate, onReset }: {
  group: SettingsGroup | undefined;
  loading: boolean;
  pending: string | null;
  onUpdate: (group: SettingsGroup, field: TaskConfigField, value: unknown) => void;
  onReset: (group: SettingsGroup) => void;
}) {
  if (!group) return <section className="settings-page"><div className="task-empty">{loading ? t("Loading") : t("No options available")}</div></section>;
  const busy = pending !== null;
  return <section className="settings-page top-level-settings-page" aria-label={t(group.name)}>
    <h1>{t(group.name)}</h1>
    {group.description && <p className="settings-description">{t(group.description)}</p>}
    <div className="surface-card top-level-settings-card">
      <div className="task-config">
        {group.fields.map((field) => <div className={`task-config-row ${field.sub_config ? "sub-config" : ""}`} key={field.key}>
          <span><strong>{t(field.key)}</strong>{field.description && <small>{t(field.description)}</small>}</span>
          <TaskConfigControl field={field} disabled={busy} onCommit={(value) => {
            if (JSON.stringify(value) !== JSON.stringify(field.value)) onUpdate(group, field, value);
          }} />
        </div>)}
        <footer><button type="button" disabled={busy} onClick={() => onReset(group)}><span className="button-label">{t("Reset Config")}</span></button></footer>
      </div>
    </div>
  </section>;
}

type ToastSink = (message: string, intent: ToastMessage["intent"]) => void;

function GithubMark() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.18.55-.39v-1.49c-2.23.49-2.7-.95-2.7-.95-.36-.93-.89-1.18-.89-1.18-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.51-1.07-1.78-.2-3.65-.89-3.65-3.96 0-.88.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.22 2.2.82A7.65 7.65 0 0 1 8 3.84c.68 0 1.35.09 1.98.27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.08-1.87 3.75-3.66 3.95.29.25.54.74.54 1.5v2.22c0 .21.15.46.55.38A8 8 0 0 0 8 0Z" /></svg>;
}

function HeartMark() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><path d="M8 14.2 2.1 8.6A4 4 0 0 1 7.8 3l.2.2.2-.2a4 4 0 0 1 5.7 5.6L8 14.2Z" /></svg>;
}

function ChatMark() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M2.2 3.2h11.6v8H7l-3.4 2v-2H2.2z" /><path d="M5 6.3h6M5 8.3h4" /></svg>;
}

function DiscordMark() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><path d="M12.9 3.2A11 11 0 0 0 10.3 2l-.4.8a9 9 0 0 0-3.8 0L5.7 2a11 11 0 0 0-2.6 1.2C1.5 5.6 1 7.9 1.2 10.1a10.5 10.5 0 0 0 3.2 1.7l.8-1.1-.8-.4.2-.2c2.2 1 4.6 1 6.8 0l.2.2-.8.4.8 1.1a10.5 10.5 0 0 0 3.2-1.7c.3-2.6-.5-4.9-1.9-6.9ZM5.8 9.1c-.7 0-1.2-.6-1.2-1.4s.5-1.4 1.2-1.4S7 7 7 7.7s-.5 1.4-1.2 1.4Zm4.4 0C9.5 9.1 9 8.5 9 7.7s.5-1.4 1.2-1.4 1.2.7 1.2 1.4-.5 1.4-1.2 1.4Z" /></svg>;
}

function ShareMark() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="4" cy="8" r="1.7" /><circle cx="12" cy="4" r="1.7" /><circle cx="12" cy="12" r="1.7" /><path d="m5.5 7.2 5-2.4m-5 4 5 2.4" /></svg>;
}

const aboutLinkOrder = ["github", "download", "discord", "qq_group", "qq_channel", "faq", "share", "sponsor"] as const;

function localizedLink(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return null;
  const values = value as Record<string, unknown>;
  const preferred = values[locale] ?? values[locale.split("_")[0]] ?? values.en_US ?? values.default;
  if (preferred !== undefined) return localizedLink(preferred);
  return Object.values(values).map(localizedLink).find(Boolean) ?? null;
}

function configuredAboutLink(links: Record<string, unknown>, name: typeof aboutLinkOrder[number]): string | null {
  const direct = localizedLink(links[name]);
  if (direct) return direct;
  const language = locale.split("_")[0];
  const localizedGroup = links[locale] ?? links[language] ?? links.default ?? links.en_US;
  if (localizedGroup && typeof localizedGroup === "object") {
    return localizedLink((localizedGroup as Record<string, unknown>)[name]);
  }
  return null;
}

function AboutLinkIcon({ name }: { name: typeof aboutLinkOrder[number] }) {
  if (name === "github") return <GithubMark />;
  if (name === "discord") return <DiscordMark />;
  if (name === "qq_group" || name === "qq_channel") return <ChatMark />;
  if (name === "faq") return <QuestionCircle20Regular />;
  if (name === "download") return <ArrowDown20Regular />;
  if (name === "sponsor") return <HeartMark />;
  if (name === "share") return <ShareMark />;
  return <Info20Regular />;
}

function sanitizedAboutHtml(html: string) {
  const documentNode = new DOMParser().parseFromString(html, "text/html");
  const allowed = new Set(["A", "B", "BLOCKQUOTE", "BR", "CODE", "DIV", "EM", "H1", "H2", "H3", "H4", "HR", "I", "LI", "OL", "P", "PRE", "SPAN", "STRONG", "U", "UL"]);
  const blockedWithContent = new Set(["EMBED", "IFRAME", "MATH", "OBJECT", "SCRIPT", "STYLE", "SVG", "TEMPLATE"]);
  for (const element of Array.from(documentNode.body.querySelectorAll("*"))) {
    if (blockedWithContent.has(element.tagName)) {
      element.remove();
      continue;
    }
    if (!allowed.has(element.tagName)) {
      element.replaceWith(...Array.from(element.childNodes));
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      if (element.tagName !== "A" || attribute.name.toLocaleLowerCase() !== "href") element.removeAttribute(attribute.name);
    }
    if (element.tagName === "A") {
      const href = element.getAttribute("href") ?? "";
      if (!/^https?:\/\//i.test(href)) element.removeAttribute("href");
      else { element.setAttribute("target", "_blank"); element.setAttribute("rel", "noreferrer noopener"); }
    }
  }
  return documentNode.body.innerHTML;
}

function compareVersions(left: string, right: string) {
  const parse = (version: string) => version.replace(/^v/, "").split(".").map(Number);
  const leftParts = parse(left);
  const rightParts = parse(right);
  if ([...leftParts, ...rightParts].some(Number.isNaN)) return left === right ? 0 : 0;
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (leftParts[index] ?? 0) - (rightParts[index] ?? 0);
    if (difference) return difference > 0 ? 1 : -1;
  }
  return 0;
}

function AboutPage({ info, updateResult, updateChecking, updateError, onCheck, notify }: {
  info: AboutInfo | null;
  updateResult: UpdateCheckResult | null;
  updateChecking: boolean;
  updateError: string | null;
  onCheck: (releaseOnly: boolean) => Promise<void>;
  notify: ToastSink;
}) {
  const [testVersions, setTestVersions] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [applying, setApplying] = useState(false);
  const [applyStatus, setApplyStatus] = useState("");
  const [applyError, setApplyError] = useState(false);
  useEffect(() => { setSelectedVersion(updateResult?.versions[0]?.version ?? ""); }, [updateResult]);
  const links = aboutLinkOrder.flatMap((name) => {
    const url = configuredAboutLink(info?.links ?? {}, name);
    return url ? [[name, url] as const] : [];
  });
  const linkLabel = (name: typeof aboutLinkOrder[number]) => name === "github" ? "GitHub" : name === "download" ? "Download" : name === "discord" ? "Discord" : name === "qq_group" ? "QQ群" : name === "qq_channel" ? "QQ频道" : name === "faq" ? "FAQ" : name === "share" ? "Share" : "Sponsor";
  const downloadUrl = configuredAboutLink(info?.links ?? {}, "download");
  const selected = updateResult?.versions.find((item) => item.version === selectedVersion);
  const direction = selected ? compareVersions(selected.version, updateResult?.current_version ?? info?.version ?? "") : 0;
  const status = updateError
    ? t("Failed to check for updates: {error}", { error: updateError })
    : updateChecking ? t("Checking for updates…")
      : !updateResult ? t("Click to check for updates")
        : !updateResult.versions.length ? t("No versions are available.")
          : updateResult.update_available ? "" : t("No updates available.");
  const apply = async () => {
    if (!selected || !direction || applying) return;
    setApplying(true);
    setApplyError(false);
    setApplyStatus(t("Starting change to {version}…", { version: selected.version }));
    try {
      await runtimeApi.applyUpdate(selected.version);
      setApplyStatus(t("Update request accepted. The app will restart to apply it."));
    } catch (reason) {
      setApplyError(true);
      setApplyStatus(t("Failed to change version: {error}", { error: reason instanceof Error ? reason.message : t("Action failed") }));
    } finally {
      setApplying(false);
    }
  };
  return <section className="settings-page about-page">
    {!info ? <div className="task-empty">{t("Loading")}</div> : <>
      <div className="surface-card about-identity">
        <div className="app-avatar">{info.icon_url ? <img src={info.icon_url} alt="" /> : "OK"}</div>
        <div><h1>{info.title}</h1><p>{info.version} · {t(info.debug ? "Debug" : "Release")}</p></div>
        {links.length > 0 && <div className="about-identity-links">{links.map(([name, url]) => name === "share" ? <button type="button" key={name} onClick={() => void navigator.clipboard.writeText(url).then(() => notify(t("Share Link copied to clipboard"), "success")).catch(() => notify(t("Action failed"), "error"))}><AboutLinkIcon name={name} />{t(linkLabel(name))}</button> : <a key={name} href={url} target="_blank" rel="noreferrer noopener"><AboutLinkIcon name={name} />{t(linkLabel(name))}</a>)}</div>}
      </div>
      {info.update_supported && <section className="about-section"><h2>{t("App update")}</h2><div className="surface-card update-card">
        <div className="update-controls">
          {updateResult && updateResult.versions.length > 0 && <label className="version-picker"><span>{t("Version")}</span><select disabled={updateChecking || applying} value={selectedVersion} style={{ width: `${Math.min(26, Math.max(12, ...updateResult.versions.map((item) => item.version.length + 6)))}ch` }} onChange={(event) => { setSelectedVersion(event.target.value); setApplyStatus(""); setApplyError(false); }}>{updateResult.versions.map((item) => <option value={item.version} key={item.version}>{item.version}</option>)}</select></label>}
          <span className={`update-status ${updateError || applyError ? "error" : ""}`} role={updateError || applyError ? "alert" : "status"}>{applyStatus || status}</span>
          {updateError && downloadUrl && <a className="update-download" href={downloadUrl} target="_blank" rel="noreferrer noopener"><ArrowDown20Regular />{t("Download")}</a>}
          <div className="update-actions"><label className="config-checkbox"><input type="checkbox" checked={testVersions} disabled={updateChecking || applying} onChange={(event) => setTestVersions(event.target.checked)} /><span className="config-checkbox-mark" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 20 20"><rect x="1" y="1" width="18" height="18" rx="3" /><path d="M5.25 10.25 8.6 13.6 14.9 6.9" /></svg></span><span>{t("Check Test Version")}</span></label><button type="button" disabled={updateChecking || applying} onClick={() => { setApplyStatus(""); setApplyError(false); void onCheck(!testVersions); }}><ArrowClockwise20Regular className={updateChecking ? "update-spinner" : undefined} />{t("Check for updates")}</button><button type="button" className="primary-button" disabled={!direction || updateChecking || applying} onClick={() => void apply()}><ArrowClockwise20Regular />{!selected || direction > 0 ? t("Update") : direction < 0 ? t("Downgrade") : t("Current version")}</button></div>
        </div>
        {selected && <div className="update-notes">{selected.notes.length ? selected.notes.map((note, index) => <div key={`${index}-${note}`}>• {note}</div>) : t("No release notes.")}</div>}
      </div></section>}
      {info.about && <section className="about-section"><h2>{t("Disclaimer")}</h2><div className="surface-card about-copy" dangerouslySetInnerHTML={{ __html: sanitizedAboutHtml(info.about) }} /></section>}
      {info.projects.length > 0 && <section className="about-projects"><h2>{t("Other Projects")}</h2><div>{info.projects.map((project) => <article className="surface-card" key={project.url}><div><strong>{t(project.name)}</strong><small>{project.url.replace("https://github.com/", "")}</small></div><nav><a href={project.url} target="_blank" rel="noreferrer noopener"><GithubMark />{t("GitHub")}</a>{project.website && <a href={project.website} target="_blank" rel="noreferrer noopener"><ArrowDown20Regular />{t("Download")}</a>}</nav></article>)}</div></section>}
    </>}
  </section>;
}

function ScriptPage({ notify, onDirtyChange, registerSave }: { notify: ToastSink; onDirtyChange: (dirty: boolean) => void; registerSave: (save: (() => Promise<boolean>) | null) => void }) {
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [templates, setTemplates] = useState<ScriptTemplate[]>([]);
  const [templateQuery, setTemplateQuery] = useState("");
  const [document, setDocument] = useState<ScriptDocument | null>(null);
  const [code, setCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [exportData, setExportData] = useState<{ tasks: string[]; manifest: Record<string, string> } | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [pendingScript, setPendingScript] = useState<string | null>(null);
  const [parameterTemplate, setParameterTemplate] = useState<ScriptTemplate | null>(null);
  const [externalDocument, setExternalDocument] = useState<ScriptDocument | null>(null);
  const recordOptions = useRef<{ loop: "none" | "count" | "forever"; count: number }>({ loop: "none", count: 10 });
  const importRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const refresh = useCallback(async () => {
    try { setScripts(await runtimeApi.scripts()); }
    catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
  }, [notify]);
  useEffect(() => {
    void refresh();
    runtimeApi.scriptTemplates().then(setTemplates).catch((reason) => notify(reason.message, "error"));
  }, [notify, refresh]);
  const dirty = Boolean(document && code !== document.code);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const loadScript = async (name: string) => {
    try { const next = await runtimeApi.script(name); setDocument(next); setCode(next.code); }
    catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
  };
  const open = async (name: string) => {
    if (dirty && name !== document?.name) { setPendingScript(name); return; }
    await loadScript(name);
  };
  const save = async () => {
    if (!document) return false;
    setBusy(true);
    try { const next = await runtimeApi.saveScript(document.name, code); setDocument(next); setCode(next.code); notify(next.error || t("Task rebuilt successfully."), next.error ? "error" : "success"); await refresh(); return !next.error; }
    catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); return false; }
    finally { setBusy(false); }
  };
  useEffect(() => { registerSave(save); return () => registerSave(null); });
  useEffect(() => {
    if (!document || busy) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      void runtimeApi.script(document.name).then((next) => {
        if (stopped || next.modified === document.modified) return;
        if (dirty) setExternalDocument(next);
        else { setDocument(next); setCode(next.code); }
      }).catch(() => undefined);
    }, 2000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [busy, dirty, document]);
  const copy = () => {
    if (!document) return;
    setBusy(true);
    void runtimeApi.copyScript(document.name).then(async (next) => { setDocument(next); setCode(next.code); await refresh(); notify(t("Task copied successfully."), "success"); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false));
  };
  const run = () => {
    if (!document) return;
    setBusy(true);
    void runtimeApi.runScript(document.name, code).then((next) => { setDocument(next); if (next.error) notify(next.error, "error"); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false));
  };
  const startRecording = (loop: "none" | "count" | "forever", count: number) => {
    recordOptions.current = { loop, count };
    setRecordOpen(false);
    setBusy(true);
    void runtimeApi.startScriptRecording().then((result) => { setRecording(true); notify(t("Recording will start when window '{name}' becomes active.", { name: result.target || "" }), "info"); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false));
  };
  const stopRecording = () => {
    setBusy(true);
    const options = recordOptions.current;
    void runtimeApi.stopScriptRecording(code, options.loop, options.count).then((result) => {
      setCode(result.code);
      setRecording(false);
      notify(t("Recording inserted into the script."), "success");
    }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false));
  };
  const errorLine = useMemo(() => {
    const match = document?.error?.match(/line\s+(\d+)/i);
    return match ? Number(match[1]) : undefined;
  }, [document?.error]);
  const insertTemplate = (template: ScriptTemplate) => {
    if (template.params.length) { setParameterTemplate(template); return; }
    insertTemplateValues(template, {});
  };
  const insertTemplateValues = (template: ScriptTemplate, values: Record<string, string>) => {
    const args = template.params.flatMap((parameter) => {
      let value = values[parameter.name]?.trim() ?? "";
      if (!value) return [];
      if (/^[A-Za-z_]\w*$/.test(value) && !["True", "False", "None"].includes(value)) value = JSON.stringify(value);
      return [parameter.default === null ? value : `${parameter.name}=${value}`];
    });
    const snippet = `${template.is_static ? `${template.class_name}.` : "self."}${template.name}(${args.join(", ")})`;
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const lineStart = code.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const indentation = code.slice(lineStart, start).match(/^\s*/)?.[0] ?? "";
    const insertion = `${start > lineStart ? "\n" : ""}${indentation || "        "}${snippet}\n`;
    setCode(`${code.slice(0, start)}${insertion}${code.slice(editor.selectionEnd)}`);
    setParameterTemplate(null);
  };
  const groupedTemplates = useMemo(() => {
    const query = templateQuery.trim().toLocaleLowerCase();
    return templates.filter((item) => !query || `${item.name} ${item.doc}`.toLocaleLowerCase().includes(query)).reduce<Record<string, ScriptTemplate[]>>((groups, item) => {
      (groups[item.category] ??= []).push(item); return groups;
    }, {});
  }, [templateQuery, templates]);
  return <section className="workspace-page script-page">
    <div className="script-workspace">
      <aside className="script-template-panel"><label className="page-search"><Search20Regular /><input value={templateQuery} onChange={(event) => setTemplateQuery(event.target.value)} placeholder={t("Search templates...")} /></label><div className="surface-card template-tree">{Object.entries(groupedTemplates).map(([category, items]) => <details key={category}><summary>{t(category)}</summary>{items.map((item) => <button type="button" key={`${item.class_name}.${item.name}`} title={item.full_doc} onClick={() => insertTemplate(item)}>{t(item.template_name)}</button>)}</details>)}</div></aside>
      <div className="script-editor-panel">
        <header className="script-toolbar">
          <label>{t("Choose Task:")}<Dropdown className="script-task-dropdown" listbox={{ className: "script-task-listbox" }} aria-label={t("Choose Task:")} inlinePopup placeholder={t("Select task to edit")} value={document?.name ?? ""} selectedOptions={document ? [document.name] : []} onOptionSelect={(_event, data) => data.optionValue && void open(data.optionValue)}>{scripts.map((script) => <Option key={script.name} value={script.name} text={script.name}>{script.name}</Option>)}</Dropdown></label>
          <Menu mountNode={window.document.querySelector(".desktop") as HTMLElement}><MenuTrigger disableButtonEnhancement><Button icon={<DocumentText20Regular />}>{t("File")}</Button></MenuTrigger><MenuPopover className="script-file-menu"><MenuList>
            <MenuItem icon={<Save20Regular />} disabled={!document || busy} onClick={() => void save()}>{t("Save")} <span className="menu-shortcut">Ctrl+S</span></MenuItem>
            <MenuItem icon={<Add20Regular />} onClick={() => setCreating(true)}>{t("Create Task")}</MenuItem>
            <MenuItem icon={<Copy20Regular />} disabled={!document || busy} onClick={copy}>{t("Copy Task")}</MenuItem>
            <MenuItem icon={<Delete20Regular />} disabled={!document || busy} onClick={() => document && setDeleteTarget(document.name)}>{t("Delete Task")}</MenuItem>
            <MenuDivider />
            <MenuItem icon={<ArrowExport20Regular />} onClick={() => void runtimeApi.scriptExportOptions().then(setExportData).catch((reason) => notify(reason.message, "error"))}>{t("Export Script")}</MenuItem>
            <MenuItem icon={<ArrowImport20Regular />} onClick={() => importRef.current?.click()}>{t("Import Script")}</MenuItem>
          </MenuList></MenuPopover></Menu>
          <input ref={importRef} hidden type="file" accept=".okscript" onChange={(event) => { const file = event.target.files?.[0]; if (file) setImportFile(file); event.currentTarget.value = ""; }} />
          <span className="toolbar-spacer" />
          <Button className="script-run-button" appearance="primary" icon={recording ? <Stop20Regular /> : <Play20Regular />} disabled={!document || busy} onClick={recording ? stopRecording : run}>{recording ? t("Stop") : t("Run")}</Button>
          {!recording && <Button icon={<Record20Regular />} disabled={!document || busy} onClick={() => setRecordOpen(true)}>{t("Record")}</Button>}
          <Button as="a" icon={<QuestionCircle20Regular />} href="https://github.com/ok-oldking/ok-py" target="_blank">{t("Guide")}</Button>
        </header>
        <div className="surface-card code-editor-wrap">{document ? <><PythonCodeEditor value={code} errorLine={errorLine} onChange={setCode} onSave={() => void save()} editorRef={editorRef} />{document.error && <div className="script-error">{document.error}</div>}</> : <div className="script-empty"><Button appearance="primary" icon={<Add20Regular />} onClick={() => setCreating(true)}>{t("Create New Task")}</Button></div>}</div>
      </div>
    </div>
    {deleteTarget && <ConfirmDeleteDialog name={deleteTarget} onCancel={() => setDeleteTarget(null)} onConfirm={() => { const name = deleteTarget; setDeleteTarget(null); setBusy(true); void runtimeApi.deleteScript(name).then(async () => { setDocument(null); setCode(""); await refresh(); notify(t("Task deleted successfully."), "success"); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false)); }} />}
    {creating && <CreateScriptDialog busy={busy} onCancel={() => setCreating(false)} onCreate={(className, taskName, description) => { setBusy(true); void runtimeApi.createScript(className, taskName, description).then(async (next) => { setDocument(next); setCode(next.code); setCreating(false); await refresh(); notify(t("Task created successfully."), "success"); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false)); }} />}
    {exportData && <ExportScriptDialog tasks={exportData.tasks} manifest={exportData.manifest} onCancel={() => setExportData(null)} onExport={(selected, fileName, scriptName, version) => { setBusy(true); void runtimeApi.exportScripts(selected, fileName, scriptName, version).then((blob) => { const url = URL.createObjectURL(blob); const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = `${fileName}.okscript`; anchor.click(); URL.revokeObjectURL(url); setExportData(null); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false)); }} />}
    {importFile && <ImportScriptDialog file={importFile} onCancel={() => setImportFile(null)} onImport={() => { const file = importFile; setBusy(true); void runtimeApi.importScripts(file).then(async (result) => { notify(result.message, "success"); setImportFile(null); await refresh(); }).catch((reason) => notify(reason.message, "error")).finally(() => setBusy(false)); }} />}
    {recordOpen && <RecordScriptDialog onCancel={() => setRecordOpen(false)} onRecord={startRecording} />}
    {parameterTemplate && <TemplateParameterDialog template={parameterTemplate} onCancel={() => setParameterTemplate(null)} onInsert={(values) => insertTemplateValues(parameterTemplate, values)} />}
    {pendingScript && <UnsavedScriptDialog onCancel={() => setPendingScript(null)} onDiscard={() => { const name = pendingScript; setPendingScript(null); void loadScript(name); }} onSave={() => { const name = pendingScript; void save().then((saved) => { if (saved) { setPendingScript(null); void loadScript(name); } }); }} />}
    {externalDocument && <ExternalScriptChangeDialog onKeep={() => { setDocument((current) => current ? { ...current, modified: externalDocument.modified } : current); setExternalDocument(null); }} onReload={() => { setDocument(externalDocument); setCode(externalDocument.code); setExternalDocument(null); }} />}
  </section>;
}

function TemplatesPage({ notify }: { notify: ToastSink }) {
  const [images, setImages] = useState<TemplateImage[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [markup, setMarkup] = useState<TemplateAnnotations | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [destination, setDestination] = useState<"tasks" | "assets">("tasks");
  const [generateEnum, setGenerateEnum] = useState(false);
  const [enumPath, setEnumPath] = useState("ok_tasks/LabelEnum.py");
  const markupOpening = useRef(false);
  const lastTemplatePress = useRef<{ name: string; time: number } | null>(null);
  const refresh = useCallback(async () => { try { setImages(await runtimeApi.templates()); } catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); } }, [notify]);
  useEffect(() => { void refresh(); }, [refresh]);
  const openMarkup = useCallback((name: string) => {
    if (markupOpening.current) return;
    markupOpening.current = true;
    void runtimeApi.templateAnnotations(name).then(setMarkup).catch((reason) => notify(reason.message, "error")).finally(() => { markupOpening.current = false; });
  }, [notify]);
  const visible = images.filter((image) => `${image.name} ${image.categories.join(" ")}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <section className="workspace-page templates-page">
    <header className="page-toolbar template-toolbar"><button type="button" className="primary-button" onClick={() => void runtimeApi.captureTemplate().then(setImages).catch((reason) => notify(reason.message, "error"))}><Camera20Regular />{t("Screenshot")}</button>{selected && <><button type="button" onClick={() => openMarkup(selected)}><Edit20Regular />{t("Markup")}</button><button type="button" onClick={() => setDeleteTarget(selected)}><Delete20Regular />{t("Delete")}</button></>}<button type="button" onClick={() => setSaveOpen(true)}><Save20Regular />{t("Save")}</button></header>
    <label className="template-search page-search"><Search20Regular /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search by name or category...")} /></label>
    <div className="template-grid">{visible.map((item) => <button type="button" className={`surface-card template-card ${selected === item.name ? "selected" : ""}`} key={item.name} onClick={() => setSelected((current) => current === item.name ? null : item.name)} onPointerDown={() => {
      const now = performance.now();
      const previous = lastTemplatePress.current;
      lastTemplatePress.current = { name: item.name, time: now };
      if (previous?.name === item.name && now - previous.time < 500) { lastTemplatePress.current = null; openMarkup(item.name); }
    }}><img src={item.url} alt={item.name} loading="lazy" /><div><strong>{item.name}</strong><small>{item.categories.join(", ")}</small></div></button>)}</div>
    {!visible.length && <div className="template-empty"><p>{t("No templates yet")}</p><button type="button" className="primary-button" onClick={() => void runtimeApi.captureTemplate().then(setImages).catch((reason) => notify(reason.message, "error"))}><Camera20Regular />{t("Take Screenshot")}</button></div>}
    {markup && <MarkupDialog initial={markup} images={images} notify={notify} onClose={() => { setMarkup(null); void refresh(); }} />}
    {deleteTarget && <ConfirmDeleteDialog name={deleteTarget} onCancel={() => setDeleteTarget(null)} onConfirm={() => {
      const name = deleteTarget;
      setDeleteTarget(null);
      void runtimeApi.deleteTemplate(name).then(async () => { setSelected(null); await refresh(); }).catch((reason) => notify(reason.message, "error"));
    }} />}
    {saveOpen && <div className="modal-backdrop"><section className="modal save-templates-modal" role="dialog" aria-modal="true"><header><strong>{t("Save To")}</strong><button type="button" onClick={() => setSaveOpen(false)}><Dismiss20Regular /></button></header><div className="save-options"><label><input type="radio" checked={destination === "tasks"} onChange={() => setDestination("tasks")} />{t("ok_tasks/assets (custom scripts)")}</label><label><input type="radio" checked={destination === "assets"} onChange={() => setDestination("assets")} />{t("assets (standalone app)")}</label><label><input type="checkbox" checked={generateEnum} onChange={(event) => setGenerateEnum(event.target.checked)} />{t("Generate label enum file")}</label>{generateEnum && <Input value={enumPath} onChange={(event) => setEnumPath(event.target.value)} placeholder={t("Relative path, e.g. ok_tasks/LabelEnum.py")} />}</div><footer className="list-editor-footer"><button type="button" onClick={() => setSaveOpen(false)}>{t("Cancel")}</button><button type="button" className="primary-button" onClick={() => void runtimeApi.saveTemplates(destination, generateEnum, enumPath).then((result) => { setSaveOpen(false); notify(result.message, "success"); }).catch((reason) => notify(reason.message, "error"))}>{t("OK")}</button></footer></section></div>}
  </section>;
}

function SchedulePage({ notify }: { notify: ToastSink }) {
  const [data, setData] = useState<ScheduleData>({ available_tasks: [], tasks: [] });
  const [creating, setCreating] = useState(false);
  const [taskIndex, setTaskIndex] = useState(0);
  const [triggerType, setTriggerType] = useState("Daily");
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [timeout, setTimeoutValue] = useState(0);
  const [intervalDays, setIntervalDays] = useState(0);
  const [intervalHours, setIntervalHours] = useState(0);
  const [autoExit, setAutoExit] = useState(true);
  const [editing, setEditing] = useState<ScheduledTask | null>(null);
  const refresh = useCallback(async () => { try { const next = await runtimeApi.schedule(); setData(next); if (!taskIndex && next.available_tasks[0]) setTaskIndex(next.available_tasks[0].index); } catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); } }, [notify, taskIndex]);
  useEffect(() => { void refresh(); }, [refresh]);
  const act = async (name: string, action: "enable" | "disable" | "delete") => { try { setData(await runtimeApi.scheduleAction(name, action)); } catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); } };
  const beginEdit = (task: ScheduledTask) => {
    setEditing(task); setTaskIndex(task.task_index); setTriggerType(task.trigger_type || "Daily"); setHour(task.start_hour ?? 9); setMinute(task.start_minute ?? 0); setTimeoutValue(task.timeout_hours ?? 0); setAutoExit(task.auto_exit ?? true); setIntervalDays(task.interval_days); setIntervalHours(task.interval_hours);
  };
  const grouped = useMemo(() => data.tasks.reduce<Record<string, ScheduledTask[]>>((groups, task) => {
    const name = task.path.replace(/^\\/, "").split("\\")[0] || t("Current App"); (groups[name] ??= []).push(task); return groups;
  }, {}), [data.tasks]);
  return <section className="workspace-page schedule-page">
    <header className="page-toolbar"><h1>{t("Schedule")}</h1><button type="button" onClick={() => void refresh()}><ArrowClockwise20Regular />{t("Refresh")}</button><button type="button" disabled={!data.available_tasks.length} onClick={() => setCreating((value) => !value)}><Add20Regular />{t("Create Task")}</button></header>
    {creating && <div className="modal-backdrop"><section className="modal schedule-edit-modal" role="dialog" aria-modal="true"><header><strong>{t("Create Schedule Task")}</strong><button type="button" onClick={() => setCreating(false)}><Dismiss20Regular /></button></header><form className="schedule-form" onSubmit={(event) => { event.preventDefault(); const selected = data.available_tasks.find((task) => task.index === taskIndex); if (!selected) return; void runtimeApi.createSchedule({ name: selected.name, task_index: taskIndex, trigger_type: triggerType, start_hour: hour, start_minute: minute, timeout_hours: timeout, auto_exit: autoExit, interval_days: intervalDays, interval_hours: intervalHours }).then((next) => { setData(next); setCreating(false); }).catch((reason) => notify(reason.message, "error")); }}>
      <label>{t("Select Task")}<select value={taskIndex} onChange={(event) => setTaskIndex(Number(event.target.value))}>{data.available_tasks.map((task) => <option key={task.index} value={task.index}>{t(task.name)}</option>)}</select></label>
      <label>{t("Trigger Type")}<select value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>{["Daily", "Weekly", "Monthly", "Once", "Custom"].map((value) => <option key={value}>{t(value)}</option>)}</select></label>
      <label>{t("Hour")}<input type="number" min="0" max="23" value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label>
      <label>{t("Minute")}<input type="number" min="0" max="59" value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label>
      <label>{t("Timeout")}<input type="number" min="0" max="12" value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} /></label>
      {triggerType === "Custom" && <><label>{t("Days")}<input type="number" min="0" max="365" value={intervalDays} onChange={(event) => setIntervalDays(Number(event.target.value))} /></label><label>{t("Hours")}<input type="number" min="0" max="23" value={intervalHours} onChange={(event) => setIntervalHours(Number(event.target.value))} /></label></>}
      <label className="schedule-check"><input type="checkbox" checked={autoExit} onChange={(event) => setAutoExit(event.target.checked)} />{t("Auto Exit After Task")}</label>
      <footer className="list-editor-footer"><button type="button" onClick={() => setCreating(false)}>{t("Cancel")}</button><button type="submit" className="primary-button">{t("Create")}</button></footer>
    </form></section></div>}
    <div className="schedule-groups">{Object.entries(grouped).map(([group, tasks]) => <section key={group}><h2>{group}</h2><div className="surface-card schedule-table-wrap"><table className="schedule-table"><thead><tr><th>{t("Task Name")}</th><th>{t("Status")}</th><th>{t("Trigger Type")}</th><th>{t("Next Run")}</th><th>{t("Enabled")}</th><th>{t("Actions")}</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.path || task.name}><td title={task.path}>{t(task.name)}</td><td>{t(task.status)}</td><td>{t(task.trigger_type)}</td><td>{task.next_run_time || "-"}</td><td><Switch checked={task.enabled} disabled={task.read_only} label="" onChange={(checked) => void act(task.path || task.name, checked ? "enable" : "disable")} /></td><td><button type="button" disabled={task.read_only} onClick={() => beginEdit(task)}>{t("Modify")}</button><button type="button" disabled={task.read_only} onClick={() => { if (window.confirm(`${t("Confirm Delete")}: ${task.name}?`)) void act(task.path || task.name, "delete"); }}>{t("Delete")}</button></td></tr>)}</tbody></table></div></section>)}</div>
    {!data.tasks.length && <div className="task-empty">{t("No options available")}</div>}
    {editing && <div className="modal-backdrop"><section className="modal schedule-edit-modal" role="dialog" aria-modal="true"><header><strong>{t("Modify Schedule Task")}</strong><button type="button" onClick={() => setEditing(null)}><Dismiss20Regular /></button></header><form className="schedule-form" onSubmit={(event) => { event.preventDefault(); void runtimeApi.updateSchedule(editing.path || editing.name, { task_index: taskIndex, trigger_type: triggerType, start_hour: hour, start_minute: minute, timeout_hours: timeout, auto_exit: autoExit, interval_days: intervalDays, interval_hours: intervalHours }).then((next) => { setData(next); setEditing(null); }).catch((reason) => notify(reason.message, "error")); }}><label>{t("Task Name")}<input disabled value={t(editing.name)} /></label><label>{t("Trigger Type")}<select value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>{["Daily", "Weekly", "Monthly", "Once", "Custom"].map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label><label>{t("Hour")}<input type="number" min="0" max="23" value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label><label>{t("Minute")}<input type="number" min="0" max="59" value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label><label>{t("Timeout")}<input type="number" min="0" max="12" value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} /></label>{triggerType === "Custom" && <><label>{t("Days")}<input type="number" min="0" max="365" value={intervalDays} onChange={(event) => setIntervalDays(Number(event.target.value))} /></label><label>{t("Hours")}<input type="number" min="0" max="23" value={intervalHours} onChange={(event) => setIntervalHours(Number(event.target.value))} /></label></>}<label className="schedule-check"><input type="checkbox" checked={autoExit} onChange={(event) => setAutoExit(event.target.checked)} />{t("Auto Exit After Task")}</label><footer className="list-editor-footer"><button type="button" onClick={() => setEditing(null)}>{t("Cancel")}</button><button type="submit" className="primary-button">{t("Confirm")}</button></footer></form></section></div>}
  </section>;
}

function RuntimeApp({ theme, language, onTheme, onLanguage }: {
  theme: AppTheme;
  language: string;
  onTheme: (theme: AppTheme) => void;
  onLanguage: (language: string) => void;
}) {
  const [nativeShell, setNativeShell] = useState(() => PYWEBVIEW_LAUNCH || Boolean(window.pywebview));
  const [initialContentLoaded, setInitialContentLoaded] = useState(false);

  useLayoutEffect(() => {
    if (!PYWEBVIEW_LAUNCH) return;
    document.documentElement.classList.add("pywebview-starting");
    return () => document.documentElement.classList.remove("pywebview-starting");
  }, []);

  useEffect(() => {
    const markNativeShell = () => {
      setNativeShell(true);
    };
    window.addEventListener("pywebviewready", markNativeShell);
    // The bridge can finish between the initial render and this effect. Check
    // it after subscribing so both sides of that race reveal the title bar.
    if (window.pywebview) markNativeShell();
    return () => window.removeEventListener("pywebviewready", markNativeShell);
  }, []);

  useEffect(() => {
    const updateDesktopScale = () => {
      // Edge can expose a several-thousand-pixel CSS viewport in desktop mode
      // when browser/display scaling is reduced. Scale the complete desktop UI
      // against the layout's reference viewport so controls remain usable.
      const widthScale = window.innerWidth / 1536;
      const heightScale = window.innerHeight / 864;
      const desiredScale = Math.max(1, Math.min(widthScale, heightScale));
      const fitScale = Math.min(window.innerWidth / 960, window.innerHeight / 640);
      const scale = Math.min(5, Math.max(0.5, Math.min(desiredScale, fitScale)));
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
  const [activePage, setActivePage] = useState("Capture");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [captureUrl, setCaptureUrl] = useState<string | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsPaused, setLogsPaused] = useState(false);
  const [logLevel, setLogLevel] = useState("ALL");
  const [logQuery, setLogQuery] = useState("");
  const [logData, setLogData] = useState<LogResponse | null>(null);
  const [tasks, setTasks] = useState<AutomationTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [settings, setSettings] = useState<SettingsGroup[]>([]);
  const [capabilities, setCapabilities] = useState<NavigationCapabilities | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [aboutInfo, setAboutInfo] = useState<AboutInfo | null>(null);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateCheckCompleted, setUpdateCheckCompleted] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [instructionsTask, setInstructionsTask] = useState<AutomationTask | null>(null);
  const [scriptDirty, setScriptDirty] = useState(false);
  const [taskTabDirty, setTaskTabDirty] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const [navIndicatorTop, setNavIndicatorTop] = useState(0);
  const [navIndicatorVisible, setNavIndicatorVisible] = useState(false);
  const [pendingPage, setPendingPage] = useState<string | null>(null);
  const scriptSaveRef = useRef<(() => Promise<boolean>) | null>(null);
  const taskTabSaveRef = useRef<(() => Promise<boolean>) | null>(null);
  const registerScriptSave = useCallback((save: (() => Promise<boolean>) | null) => { scriptSaveRef.current = save; }, []);
  const registerTaskTabSave = useCallback((save: (() => Promise<boolean>) | null) => { taskTabSaveRef.current = save; }, []);
  const logConsole = useRef<HTMLPreElement>(null);
  const captureDialog = useRef<HTMLElement>(null);
  const logDialog = useRef<HTMLElement>(null);
  const instructionsDialog = useRef<HTMLElement>(null);
  const nextToastId = useRef(0);
  const toastTimers = useRef<Map<number, number>>(new Map());
  const toastKeys = useRef<Map<number, string>>(new Map());
  const activeToastMessages = useRef<Set<string>>(new Set());
  const updateRequestPending = useRef(false);
  const scheduledUpdateTimer = useRef<number | null>(null);
  const eventSessionKey = ui?.event_session_key;
  const systemNotificationsEnabled = settings.some((group) =>
    group.name === "Notification" && group.fields.some((field) =>
      field.key === SYSTEM_NOTIFICATION_KEY && field.value === true
    )
  );
  const closeCapture = useCallback(() => setCaptureUrl(null), []);
  const closeLogs = useCallback(() => setLogsOpen(false), []);
  const closeInstructions = useCallback(() => setInstructionsTask(null), []);
  const pushToast = useCallback((message: string, intent: ToastMessage["intent"]) => {
    const normalizedMessage = message.trim();
    if (!normalizedMessage) return;
    const messageKey = normalizedMessage.toLocaleLowerCase();
    if (activeToastMessages.current.has(messageKey)) return;
    activeToastMessages.current.add(messageKey);
    const toast = { id: ++nextToastId.current, message: normalizedMessage, intent };
    toastKeys.current.set(toast.id, messageKey);
    setToasts((current) => [toast, ...current]);
    if (intent !== "success") {
      const timer = window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== toast.id));
        toastTimers.current.delete(toast.id);
        toastKeys.current.delete(toast.id);
        activeToastMessages.current.delete(messageKey);
      }, 15_000);
      toastTimers.current.set(toast.id, timer);
    }
  }, []);
  const dismissToast = useCallback((id: number) => {
    const timer = toastTimers.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    toastTimers.current.delete(id);
    const messageKey = toastKeys.current.get(id);
    if (messageKey !== undefined) activeToastMessages.current.delete(messageKey);
    toastKeys.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  useEffect(() => () => {
    toastTimers.current.forEach((timer) => window.clearTimeout(timer));
    toastTimers.current.clear();
    toastKeys.current.clear();
    activeToastMessages.current.clear();
  }, []);

  useDialogFocus(captureUrl !== null, captureDialog, closeCapture);
  useDialogFocus(logsOpen, logDialog, closeLogs);
  useDialogFocus(instructionsTask !== null, instructionsDialog, closeInstructions);

  const load = useCallback(async () => {
    try {
      setUi(await runtimeApi.captureUi());
    } catch (reason) {
      pushToast(reason instanceof Error ? reason.message : t("Could not reach the automation runtime"), "error");
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

  const loadTasks = useCallback(async (showLoading = false) => {
    if (showLoading) setTasksLoading(true);
    try {
      setTasks(await runtimeApi.tasks());
    } catch (reason) {
      pushToast(reason instanceof Error ? reason.message : t("Could not reach the automation runtime"), "error");
    } finally {
      if (showLoading) setTasksLoading(false);
    }
  }, [pushToast]);

  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    try { setSettings(await runtimeApi.settings()); }
    catch (reason) { pushToast(reason instanceof Error ? reason.message : t("Could not reach the automation runtime"), "error"); }
    finally { setSettingsLoading(false); }
  }, [pushToast]);

  const checkForUpdates = useCallback(async (releaseOnly = true, manual = true) => {
    if (manual && scheduledUpdateTimer.current !== null) {
      window.clearTimeout(scheduledUpdateTimer.current);
      scheduledUpdateTimer.current = null;
    }
    if (updateRequestPending.current) return;
    updateRequestPending.current = true;
    setUpdateChecking(true);
    setUpdateCheckCompleted(false);
    setUpdateError(null);
    try {
      setUpdateResult(await runtimeApi.updates(releaseOnly));
    } catch (reason) {
      setUpdateResult(null);
      setUpdateError(reason instanceof Error ? reason.message : t("Action failed"));
    } finally {
      updateRequestPending.current = false;
      setUpdateChecking(false);
      setUpdateCheckCompleted(true);
    }
  }, []);

  useEffect(() => {
    let active = true;
    runtimeApi.about().then((value) => { if (active) setAboutInfo(value); }).catch((reason) => {
      if (active) pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
    });
    return () => { active = false; };
  }, [pushToast]);

  useEffect(() => {
    if (!aboutInfo?.update_supported || updateChecking || updateCheckCompleted) return;
    scheduledUpdateTimer.current = window.setTimeout(() => {
      scheduledUpdateTimer.current = null;
      void checkForUpdates(true, false);
    }, aboutInfo.update_check_delay_ms);
    return () => {
      if (scheduledUpdateTimer.current !== null) {
        window.clearTimeout(scheduledUpdateTimer.current);
        scheduledUpdateTimer.current = null;
      }
    };
  }, [aboutInfo, checkForUpdates, updateCheckCompleted, updateChecking]);

  useEffect(() => {
    let active = true;
    const loadNavigation = () => runtimeApi.navigation().then(setCapabilities).catch((reason) => {
      pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
    });
    void Promise.allSettled([load(), loadSettings(), loadNavigation()]).then(() => {
      if (active) setInitialContentLoaded(true);
    });
    return () => { active = false; };
  }, [load, loadSettings, pushToast]);

  useEffect(() => {
    if (!initialContentLoaded) return;
    let secondFrame = 0;
    let revealFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        document.documentElement.classList.remove("pywebview-starting");
        revealFrame = window.requestAnimationFrame(() => {
          void runtimeApi.contentReady();
        });
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
      if (revealFrame) window.cancelAnimationFrame(revealFrame);
    };
  }, [initialContentLoaded]);

  useEffect(() => {
    if (!systemNotificationsEnabled || !("Notification" in window) || Notification.permission !== "default") return;
    const requestPermission = () => { void requestBrowserNotificationPermission(); };
    window.addEventListener("pointerdown", requestPermission, { once: true });
    window.addEventListener("keydown", requestPermission, { once: true });
    return () => {
      window.removeEventListener("pointerdown", requestPermission);
      window.removeEventListener("keydown", requestPermission);
    };
  }, [systemNotificationsEnabled]);
  useEffect(() => {
    if (activePage === "Tasks" || activePage === "Triggers" || activePage.startsWith("group:")) void loadTasks(true);
    if (activePage === "Settings") void loadSettings();
  }, [activePage, loadSettings, loadTasks]);

  useEffect(() => {
    if (activePage !== "Tasks" && activePage !== "Triggers" && !activePage.startsWith("group:")) return;
    const timer = window.setInterval(() => void loadTasks(), 1000);
    return () => window.clearInterval(timer);
  }, [activePage, loadTasks]);

  useEffect(() => {
    if (!logsOpen || logsPaused) return;
    let stopped = false;
    let timer: number | undefined;
    const refreshLogs = async () => {
      try {
        const data = await runtimeApi.logs(logLevel, logQuery);
        if (!stopped) setLogData(data);
      } catch (reason) {
        if (!stopped) pushToast(reason instanceof Error ? reason.message : t("Could not load logs"), "error");
      } finally {
        if (!stopped) timer = window.setTimeout(refreshLogs, 750);
      }
    };
    void refreshLogs();
    return () => { stopped = true; if (timer) clearTimeout(timer); };
  }, [logLevel, logQuery, logsOpen, logsPaused, pushToast]);

  useEffect(() => {
    const consoleElement = logConsole.current;
    if (consoleElement && !logsPaused) consoleElement.scrollTop = consoleElement.scrollHeight;
  }, [logData, logsPaused]);

  useEffect(() => {
    if (!eventSessionKey) return;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let stopped = false;
    const connect = () => {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${location.host}/api/events?session_key=${encodeURIComponent(eventSessionKey)}`);
      socket.onmessage = ({ data }) => {
        let event: RuntimeEvent;
        try { event = JSON.parse(data) as RuntimeEvent; }
        catch { return; }
        if (event.event === "notification") {
          const rawMessage = typeof event.args[0] === "string" ? event.args[0] : String(event.args[0] ?? "");
          const message = formatEventText(t(rawMessage), event.args[5]);
          const rawTitle = typeof event.args[1] === "string" ? event.args[1] : "";
          const title = rawTitle ? t(rawTitle) : (ui?.title || "ok-script");
          pushToast(message, event.args[2] === true ? "error" : "info");
          if (event.args[3] === true && systemNotificationsEnabled) {
            showBrowserNotification(title, message, ui?.icon_url);
          }
        }
        if (captureStateEvents.has(event.event)) {
          // The server attaches the new UI state for relevant events. Do not
          // follow every event with another HTTP request.
          if (event.ui) setUi(event.ui);
          if (event.event === "adb_devices") setPending((current) => current === "refresh" ? null : current);
        }
        if (taskStateEvents.has(event.event)) {
          void loadTasks();
          if (event.event === "task_list_updated") runtimeApi.navigation().then(setCapabilities).catch(() => undefined);
          if (!event.ui) void load();
        }
        if (event.event === "task_tab") {
          publishTaskTabEvent({
            tab_id: String(event.args[0] ?? ""),
            name: String(event.args[1] ?? ""),
            payload: event.args[2]
          });
        }
      };
      socket.onclose = () => {
        if (!stopped) timer = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [eventSessionKey, load, loadTasks, pushToast, systemNotificationsEnabled, ui?.icon_url, ui?.title]);

  const perform = async (name: string, action: () => Promise<CaptureUiState>) => {
    setPending(name);
    try { setUi(await action()); }
    catch (reason) { pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
    finally { setPending(null); }
  };

  const tool = async (name: string) => {
    setPending(name);
    try {
      const result = await runtimeApi.tool(name);
      pushToast(result.message, "success");
      if (result.kind === "capture" && result.resource_url) setCaptureUrl(result.resource_url);
    } catch (reason) { pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
    finally { setPending(null); }
  };

  const refreshDevices = async () => {
    setPending("refresh");
    try {
      await runtimeApi.refreshDevices();
      // Completion and the updated device list arrive through adb_devices.
    } catch (reason) {
      setPending(null);
      pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
    }
  };

  const performTask = async (name: string, action: () => Promise<unknown>) => {
    setPending(name);
    try {
      await action();
      const [nextUi, nextTasks] = await Promise.all([runtimeApi.captureUi(), runtimeApi.tasks()]);
      setUi(nextUi);
      setTasks(nextTasks);
    } catch (reason) {
      pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
    } finally {
      setPending(null);
    }
  };

  const replaceTask = (updated: AutomationTask) => {
    setTasks((current) => current.map((task) => task.class_name === updated.class_name ? updated : task));
  };

  const updateTaskConfig = async (task: AutomationTask, field: TaskConfigField, value: unknown) => {
    setTasks((current) => current.map((item) => item.class_name === task.class_name ? {
      ...item,
      config: item.config.map((configField) => configField.key === field.key ? { ...configField, value } : configField)
    } : item));
    try {
      replaceTask(await runtimeApi.setTaskConfig(task.name, field.key, value));
    } catch (reason) {
      pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
      void loadTasks();
    }
  };

  const resetTaskConfig = async (task: AutomationTask) => {
    try {
      replaceTask(await runtimeApi.resetTaskConfig(task.name));
    } catch (reason) {
      pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error");
    }
  };

  const replaceSettingsGroup = (updated: SettingsGroup) => {
    setSettings((current) => current.map((group) => group.name === updated.name ? updated : group));
  };

  const updateSetting = async (group: SettingsGroup, field: TaskConfigField, value: unknown) => {
    setPending(`setting:${group.name}:${field.key}`);
    setSettings((current) => current.map((item) => item.name === group.name ? {
      ...item, fields: item.fields.map((itemField) => itemField.key === field.key ? { ...itemField, value } : itemField)
    } : item));
    try {
      if (group.name === "Notification" && field.key === SYSTEM_NOTIFICATION_KEY && value === true) {
        await requestBrowserNotificationPermission();
      }
      replaceSettingsGroup(await runtimeApi.setSetting(group.name, field.key, value));
    }
    catch (reason) { pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error"); void loadSettings(); }
    finally { setPending(null); }
  };

  const resetSettings = async (group: SettingsGroup) => {
    setPending(`setting:${group.name}:reset`);
    try { replaceSettingsGroup(await runtimeApi.resetSettings(group.name)); }
    catch (reason) { pushToast(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
    finally { setPending(null); }
  };

  const devices = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return (ui?.devices ?? []).filter((device) => !normalized || `${device.label} ${device.keywords}`.toLocaleLowerCase().includes(normalized));
  }, [query, ui?.devices]);

  const visibleTasks = useMemo(() => tasks.filter((task) => {
    if (!task.visible) return false;
    if (activePage === "Triggers") return task.trigger;
    if (activePage.startsWith("group:")) return !task.trigger && task.group_name === activePage.slice(6);
    return activePage === "Tasks" && !task.trigger && !task.group_name;
  }), [activePage, tasks]);
  const topLevelSettings = useMemo(() => settings.filter((group) => group.top_level), [settings]);
  const taskGroups = useMemo(() => Array.from(new Set(tasks.filter((task) => task.visible && !task.trigger && task.group_name).map((task) => task.group_name as string))), [tasks]);
  const topLevelGroupForPage = useCallback((page: string) => topLevelSettings.find((group) =>
    group.name === page || (group.name === "Notification" && page === "Notifications")
  ), [topLevelSettings]);
  const primaryNavigationItems = useMemo(() => {
    const items = [...primaryNavigation];
    const taskTabs = capabilities?.task_tabs ?? [];
    const beforeDefaultTaskTabs = taskTabs.filter((tab) =>
      tab.position === "scroll" && !tab.add_after_default_tabs
    );
    const afterDefaultTaskTabs = taskTabs.filter((tab) =>
      tab.position === "scroll" && tab.add_after_default_tabs
    );
    beforeDefaultTaskTabs.forEach((tab) => {
      items.push([`task-tab:${tab.id}`, taskTabIcon(tab.icon)]);
    });
    if (capabilities?.triggers) items.push(["Triggers", Timer20Regular]);
    if (capabilities?.tasks) items.push(["Tasks", TaskListSquareLtr20Regular]);
    taskGroups.forEach((group) => items.push([`group:${group}`, TaskListSquareLtr20Regular]));
    afterDefaultTaskTabs.forEach((tab) => {
      items.push([`task-tab:${tab.id}`, taskTabIcon(tab.icon)]);
    });
    if (capabilities?.script) items.push(["Script", Edit20Regular]);
    if (capabilities?.templates) items.push(["Templates", Image20Regular]);
    if (capabilities?.schedule) items.push(["Schedule", Calendar20Regular]);
    topLevelSettings.filter((group) => group.name !== "Notification").forEach((group) => {
      if (!items.some(([label]) => label === group.name)) items.push([group.name, Settings20Regular]);
    });
    return items;
  }, [capabilities, taskGroups, topLevelSettings]);
  const secondaryNavigationItems = useMemo(() => {
    const taskTabs = (capabilities?.task_tabs ?? [])
      .filter((tab) => tab.position === "bottom")
      .map((tab): [string, IconComponent] => [`task-tab:${tab.id}`, taskTabIcon(tab.icon)]);
    return [...taskTabs, ...secondaryNavigation];
  }, [capabilities]);
  const activeTaskTab = useMemo(() => {
    if (!activePage.startsWith("task-tab:")) return null;
    const id = activePage.slice("task-tab:".length);
    return capabilities?.task_tabs.find((tab) => tab.id === id) ?? null;
  }, [activePage, capabilities]);
  const activeTopLevelSettings = topLevelGroupForPage(activePage);
  const navigationLabel = (label: string) => {
    if (label.startsWith("group:")) return label.slice(6);
    if (label.startsWith("task-tab:")) {
      const id = label.slice("task-tab:".length);
      return t(capabilities?.task_tabs.find((tab) => tab.id === id)?.name ?? id);
    }
    return t(label);
  };
  const navigate = (page: string) => {
    const dirtyScript = activePage === "Script" && page !== "Script" && scriptDirty;
    const dirtyTaskTab = activePage.startsWith("task-tab:") && page !== activePage && taskTabDirty;
    if (dirtyScript || dirtyTaskTab) setPendingPage(page);
    else setActivePage(page);
  };

  const status = ui?.status;
  const startLabel = status?.starting ? t("Starting") : status?.paused === false ? t("Pause") : `${t("Start")}${status?.hotkey ? `(${status.hotkey})` : ""}`;
  const StartStateIcon = status?.starting ? ArrowClockwise20Regular : status?.paused === false ? Pause20Regular : Play20Regular;

  const callWindowApi = (action: keyof PywebviewWindowApi) => {
    const method = window.pywebview?.api?.[action];
    if (method) void method();
  };

  useLayoutEffect(() => {
    const activeItem = sidebarRef.current?.querySelector<HTMLElement>(".nav-item.active");
    if (!activeItem) {
      setNavIndicatorVisible(false);
      return;
    }
    setNavIndicatorTop(activeItem.offsetTop + (activeItem.offsetHeight - 18) / 2);
    setNavIndicatorVisible(true);
  }, [activePage, collapsed, primaryNavigationItems]);

  return <div className={`desktop ${collapsed ? "nav-collapsed" : ""} ${nativeShell ? "pywebview-shell" : ""}`}>
    <header className="window-titlebar" aria-hidden={!nativeShell}>
      <div className="window-titlebar-drag pywebview-drag-region" onDoubleClick={() => callWindowApi("toggle_maximize")}>
        {ui?.icon_url ? <img src={ui.icon_url} alt="" /> : <span className="window-titlebar-fallback">OK</span>}
        <span className="window-titlebar-title">{ui?.title || "ok-script"}</span>
      </div>
      <div className="window-controls">
        <button type="button" aria-label={t("Minimize")} title={t("Minimize")} onClick={() => callWindowApi("minimize")}><Subtract20Regular /></button>
        <button type="button" aria-label={t("Maximize")} title={t("Maximize")} onClick={() => callWindowApi("toggle_maximize")}><Square20Regular /></button>
        <button type="button" className="window-close" aria-label={t("Close")} title={t("Close")} onClick={() => callWindowApi("close")}><Dismiss20Regular /></button>
      </div>
    </header>
    <aside ref={sidebarRef} className="sidebar">
      <span
        className={`nav-selection-indicator ${navIndicatorVisible ? "visible" : ""}`}
        style={{ transform: `translateY(${navIndicatorTop}px)` }}
        aria-hidden="true"
      />
      <button type="button" className="nav-toggle" aria-label={t("Toggle navigation")} onClick={() => setCollapsed((value) => !value)}><Navigation20Regular /></button>
      <nav className="nav-primary">
        {primaryNavigationItems.map(([label, Icon]) => <button
          type="button"
          key={label}
          className={`nav-item ${label === activePage ? "active" : ""}`}
          aria-current={label === activePage ? "page" : undefined}
          title={navigationLabel(label)}
          onClick={() => {
            navigate(label);
          }}
        ><Icon className={opticallyHighNavigationIcons.has(label) ? "nav-icon-shift-down" : undefined} /><span>{navigationLabel(label)}</span></button>)}
      </nav>
      <nav className="nav-secondary">
        {secondaryNavigationItems.map(([label, Icon]) => <button type="button" key={label} className={`nav-item ${label === activePage ? "active" : ""}`} aria-current={label === activePage ? "page" : undefined} title={navigationLabel(label)} onClick={() => {
          navigate(label);
        }}><Icon /><span>{navigationLabel(label)}</span>{label === "About" && updateCheckCompleted && updateResult?.update_available && <i className="nav-update-dot" aria-label={t("Update available.")} />}</button>)}
      </nav>
    </aside>

    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => <div key={toast.id} className={`toast toast-${toast.intent}`} role={toast.intent === "error" ? "alert" : "status"}>
        {toast.intent === "error" ? <ErrorCircle20Regular /> : toast.intent === "success" ? <CheckmarkCircle20Regular /> : <Info20Regular />}
        <span>{toast.message}</span>
        <button type="button" aria-label={t("Close")} onClick={() => dismissToast(toast.id)}><Dismiss20Regular /></button>
      </div>)}
    </div>

    <main key={activePage} className={`content nav-page-transition ${activePage !== "Capture" ? "task-content" : ""}`}>
      {activePage === "Capture" ? <>
      <section className="start-card about-identity surface-card">
        <div className="app-avatar">{ui?.icon_url ? <img src={ui.icon_url} alt="" /> : "OK"}</div><div><h1>{ui?.title || "OK-WW"}</h1><p>{ui?.version || "dev"} · {t(ui?.debug ? "Debug" : "Release")}</p></div>
        <div className="start-actions">
          <button type="button" disabled={pending !== null} onClick={() => void tool("capture")}><Camera20Regular />{t("Capture")}</button>
          <button type="button" disabled={pending !== null} onClick={() => void refreshDevices()}><ArrowClockwise20Regular />{pending === "refresh" ? t("Refreshing") : t("Refresh")}</button>
          <button className="primary-button" type="button" disabled={pending !== null || loading || status?.starting} onClick={() => void perform("start", status?.paused === false ? async () => { await runtimeApi.pause(); return runtimeApi.captureUi(); } : async () => { await runtimeApi.resume(); return runtimeApi.captureUi(); })}><StartStateIcon />{startLabel}</button>
        </div>
      </section>

      <section className="selectors">
        <div className="selector-column window-column">
          <h2>{t("Choose Window")}</h2>
          <div className="surface-card selector-card">
            <label className="device-search"><Search20Regular /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search title or exe...")} /></label>
            <div className="option-list" role="group" aria-label={t("Choose Window")}>
              {devices.map((device) => <button
                type="button"
                aria-pressed={device.selected}
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
          <div className="surface-card selector-card"><MethodList items={ui?.capture_methods ?? []} label={t("Capture Method")} disabled={pending !== null} onSelect={(id) => void perform("capture-method", () => runtimeApi.selectCapture(id))} /></div>
        </div>
        <div className="selector-column">
          <h2>{t("Choose Interaction")}</h2>
          <div className="surface-card selector-card"><MethodList items={ui?.interaction_methods ?? []} label={t("Choose Interaction")} disabled={pending !== null} onSelect={(id) => void perform("interaction-method", () => runtimeApi.selectInteraction(id))} /></div>
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
          {ui && <Switch checked={ui.overlay.boxes} disabled={pending !== null} label={t("Enable Boxes")} onChange={(value) => void perform("overlay", () => runtimeApi.setOverlay("boxes", value))} />}
        </div>
      </section>
      <div className="content-spacer" />
      </> : activePage === "About" ? <AboutPage info={aboutInfo} updateResult={updateResult} updateChecking={updateChecking} updateError={updateError} onCheck={(releaseOnly) => checkForUpdates(releaseOnly, true)} notify={pushToast} />
      : activeTaskTab ? <TaskTabHost
        tab={activeTaskTab}
        notify={pushToast}
        onDirtyChange={setTaskTabDirty}
        registerSave={registerTaskTabSave}
      />
      : activePage === "Script" ? <ScriptPage notify={pushToast} onDirtyChange={setScriptDirty} registerSave={registerScriptSave} />
      : activePage === "Templates" ? <TemplatesPage notify={pushToast} />
      : activePage === "Schedule" ? <SchedulePage notify={pushToast} />
      : activePage === "Settings" ? <SettingsPage
        groups={settings}
        loading={settingsLoading}
        pending={pending}
        theme={theme}
        language={language}
        onTheme={onTheme}
        onLanguage={onLanguage}
        onUpdate={(group, field, value) => void updateSetting(group, field, value)}
        onReset={(group) => void resetSettings(group)}
      /> : activeTopLevelSettings || activePage === "Notifications" ? <TopLevelSettingsPage
        group={activeTopLevelSettings}
        loading={settingsLoading}
        pending={pending}
        onUpdate={(group, field, value) => void updateSetting(group, field, value)}
        onReset={(group) => void resetSettings(group)}
      /> : <>
        <section className="task-list" aria-label={t(activePage)}>
          {tasksLoading && !tasks.length ? <div className="task-empty">{t("Loading")}</div> : visibleTasks.length ? visibleTasks.map((task) => {
            const expanded = expandedTasks.has(task.class_name);
            const busy = pending !== null;
            const toggleExpanded = () => setExpandedTasks((current) => {
              const next = new Set(current);
              if (next.has(task.class_name)) next.delete(task.class_name); else next.add(task.class_name);
              return next;
            });
            const elapsed = task.running && task.start_time > 0 ? Math.max(0, Date.now() / 1000 - task.start_time) : 0;
            const elapsedText = `${Math.floor(elapsed / 3600)}h ${Math.floor(elapsed % 3600 / 60)}m ${Math.floor(elapsed % 60)}s`;
            const description = task.running
              ? `${task.paused ? t("Paused") : t("Running")} · ${t("Time Elapsed")}: ${elapsedText}`
              : task.description;
            return <article key={task.class_name} className={`qt-task-card surface-card ${expanded ? "expanded" : ""} ${task.running ? "running" : ""}`}>
              <div className="qt-task-header">
                <button type="button" className="task-summary" disabled={!task.config.length} aria-expanded={task.config.length ? expanded : undefined} onClick={toggleExpanded}><span><strong>{task.name}</strong><small>{description}</small></span></button>
                <div className="qt-task-actions">
                  {task.waiting_for && <span className="task-waiting" title={t("Waiting for {task_name} task to be completed", { task_name: task.waiting_for })}>{t("Waiting for {task_name} task to be completed", { task_name: task.waiting_for })}</span>}
                  {task.instructions && <button type="button" disabled={busy} onClick={() => setInstructionsTask(task)}><Info20Regular /><span className="button-label">{t("Instructions")}</span></button>}
                  {task.trigger ? <Switch checked={task.enabled} disabled={busy} label={task.enabled ? t("Enabled") : t("Disabled")} onChange={(checked) => void performTask(task.name, () => runtimeApi.taskAction(task.name, checked ? "enable" : "disable"))} /> : <>
                    {task.enabled && task.running && !task.paused && <button type="button" disabled={busy} onClick={() => void performTask(task.name, () => runtimeApi.taskAction(task.name, "pause"))}><Pause20Regular /><span className="button-label">{t("Pause")}</span></button>}
                    {task.enabled && <button type="button" className="primary-button" disabled={busy} onClick={() => void performTask(task.name, () => runtimeApi.taskAction(task.name, "stop"))}><Stop20Regular /><span className="button-label">{t("Stop")}</span></button>}
                    {(!task.enabled || task.paused) && <button type="button" className="primary-button" disabled={busy} onClick={() => void performTask(task.name, task.paused ? () => runtimeApi.taskAction(task.name, "resume") : () => runtimeApi.startTask(task.name))}><Play20Regular /><span className="button-label">{task.paused ? t("Resume") : t("Start")}</span></button>}
                  </>}
                </div>
                {task.config.length > 0 && <button type="button" className="task-expand-indicator" aria-label={task.name} aria-expanded={expanded} onClick={toggleExpanded}><ChevronDown20Regular /></button>}
              </div>
              {expanded && task.config.length > 0 && <div className="task-config">
                {task.config.map((field) => <div className={`task-config-row ${field.sub_config ? "sub-config" : ""}`} key={field.key}>
                  <span><strong>{field.key}</strong>{field.description && <small>{field.description}</small>}</span>
                  <TaskConfigControl field={field} disabled={busy} onCommit={(value) => {
                    if (JSON.stringify(value) !== JSON.stringify(field.value)) void updateTaskConfig(task, field, value);
                  }} />
                </div>)}
                <footer><button type="button" disabled={busy} onClick={() => void resetTaskConfig(task)}><span className="button-label">{t("Reset Config")}</span></button></footer>
              </div>}
            </article>;
          }) : <div className="task-empty">{t("{count} available", { count: 0 })}</div>}
        </section>
      </>}
    </main>
    {captureUrl && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeCapture()}>
      <section ref={captureDialog} className="modal capture-modal" role="dialog" aria-modal="true" aria-label={t("Capture Preview")} tabIndex={-1}>
        <header><strong>{t("Capture Preview")}</strong><div className="modal-header-actions"><button className="modal-text-button" type="button" onClick={() => void tool("screenshot-folder")}><Folder20Regular />{t("Open Screenshot Folder")}</button><button type="button" aria-label={t("Close")} onClick={closeCapture}><Dismiss20Regular /></button></div></header>
        <div className="capture-preview"><img src={captureUrl} alt={t("Captured game frame")} /></div>
      </section>
    </div>}
    {instructionsTask && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeInstructions()}>
      <section ref={instructionsDialog} className="modal instructions-modal" role="dialog" aria-modal="true" aria-label={instructionsTask.name} tabIndex={-1}>
        <header><strong>{instructionsTask.name}</strong><button type="button" aria-label={t("Close")} onClick={closeInstructions}><Dismiss20Regular /></button></header>
        <div>{instructionsTask.instructions}</div>
      </section>
    </div>}
    {logsOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeLogs()}>
      <section ref={logDialog} className="modal log-modal" role="dialog" aria-modal="true" aria-label={t("View Log")} tabIndex={-1}>
        <header><strong>{t("View Log")}</strong><button type="button" aria-label={t("Close")} onClick={closeLogs}><Dismiss20Regular /></button></header>
        <div className="log-toolbar">
          <select aria-label={t("Log level")} value={logLevel} onChange={(event) => setLogLevel(event.target.value)}>
            <option value="ALL">{t("All Levels")}</option><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option><option>CRITICAL</option>
          </select>
          <label><Search20Regular /><input data-autofocus aria-label={t("Filter logs...")} value={logQuery} onChange={(event) => setLogQuery(event.target.value)} placeholder={t("Filter logs...")} /></label>
          <button type="button" onClick={() => setLogsPaused((value) => !value)}>{logsPaused ? <Play20Regular /> : <Pause20Regular />}{logsPaused ? t("Resume") : t("Pause")}</button>
          <button type="button" onClick={() => { setLogsPaused(true); setLogData((current) => current ? { ...current, text: "", line_count: 0 } : current); }}><Dismiss20Regular />{t("Clear")}</button>
        </div>
        <pre ref={logConsole} className="log-console">{logData?.text || t("Waiting for ok-script.log")}</pre>
        <footer>{logData?.path || "logs/ok-script.log"} · {logData?.line_count ?? 0} {t("lines")}</footer>
      </section>
    </div>}
    {pendingPage && <UnsavedScriptDialog
      onCancel={() => setPendingPage(null)}
      onDiscard={() => {
        const page = pendingPage;
        setPendingPage(null);
        if (activePage === "Script") setScriptDirty(false);
        else setTaskTabDirty(false);
        setActivePage(page);
      }}
      onSave={() => {
        const page = pendingPage;
        const save = activePage === "Script" ? scriptSaveRef.current : taskTabSaveRef.current;
        if (!save) return;
        void save().then((saved) => {
          if (!saved) return;
          setPendingPage(null);
          if (activePage === "Script") setScriptDirty(false);
          else setTaskTabDirty(false);
          setActivePage(page);
        });
      }}
    />}
    <div className="theme-mark"><WeatherMoon20Regular /><Window20Regular /></div>
  </div>;
}

export default function App() {
  const [theme, setTheme] = useState<AppTheme>(() => (localStorage.getItem("ok-script-theme") as AppTheme | null) ?? "Auto");
  const [language, setLanguage] = useState(() => {
    const initial = localStorage.getItem("ok-script-language") ?? "Auto";
    setLocale(initial);
    return initial;
  });
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  const [systemAccent, setSystemAccent] = useState<SystemAccent | null>(null);
  const dark = theme === "Dark" || (theme === "Auto" && systemDark);
  const accent = theme === "Auto" ? (systemAccent?.[dark ? "dark" : "light"] ?? WINDOWS_STANDARD_BLUE) : WINDOWS_STANDARD_BLUE;

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    let stopped = false;
    const loadAccent = async () => {
      try {
        const value = (await runtimeApi.themeUi()).system_accent;
        if (!stopped && value && /^#[0-9a-f]{6}$/i.test(value.light) && /^#[0-9a-f]{6}$/i.test(value.dark)) setSystemAccent(value);
      } catch {
        if (!stopped) setSystemAccent(null);
      }
    };
    void loadAccent();
    window.addEventListener("focus", loadAccent);
    return () => { stopped = true; window.removeEventListener("focus", loadAccent); };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.style.setProperty("--accent", accent);
    document.documentElement.style.setProperty("--accent-hover", mixHex(accent, "#ffffff", 0.14));
    localStorage.setItem("ok-script-theme", theme);
  }, [accent, dark, theme]);

  useEffect(() => {
    localStorage.setItem("ok-script-language", language);
  }, [language]);

  return <FluentProvider theme={themed(dark ? webDarkTheme : webLightTheme, dark, accent)} className="app-provider">
    <RuntimeApp theme={theme} language={language} onTheme={setTheme} onLanguage={(next) => { setLocale(next); setLanguage(next); }} />
  </FluentProvider>;
}
