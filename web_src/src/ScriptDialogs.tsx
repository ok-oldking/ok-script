import { useEffect, useState } from "react";
import { Button, Checkbox, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Input } from "@fluentui/react-components";
import { t } from "./i18n";
import type { ScriptTemplate } from "./types";

export function UnsavedScriptDialog({ onCancel, onDiscard, onSave }: {
  onCancel: () => void;
  onDiscard: () => void;
  onSave: () => void;
}) {
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog"><DialogBody>
      <DialogTitle>{t("Save Changes")}</DialogTitle>
      <DialogContent>{t("The current task has unsaved changes. Do you want to save them?")}</DialogContent>
      <DialogActions><Button onClick={onCancel}>{t("Cancel")}</Button><Button onClick={onDiscard}>{t("Don't Save")}</Button><Button appearance="primary" onClick={onSave}>{t("Save")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function ExternalScriptChangeDialog({ onKeep, onReload }: {
  onKeep: () => void;
  onReload: () => void;
}) {
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onKeep()}>
    <DialogSurface className="script-action-dialog"><DialogBody>
      <DialogTitle>{t("File Changed")}</DialogTitle>
      <DialogContent>{t("The file was modified externally. Reload it and discard your unsaved changes?")}</DialogContent>
      <DialogActions><Button onClick={onKeep}>{t("Keep Editing")}</Button><Button appearance="primary" onClick={onReload}>{t("Reload")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function TemplateParameterDialog({ template, onCancel, onInsert }: {
  template: ScriptTemplate;
  onCancel: () => void;
  onInsert: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const missing = template.params.some((parameter) => parameter.default === null && !values[parameter.name]?.trim());
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog template-parameter-dialog"><DialogBody>
      <DialogTitle>{template.name}</DialogTitle>
      <DialogContent className="script-dialog-content">
        {template.full_doc && <pre className="template-parameter-doc">{template.full_doc}</pre>}
        {template.params.map((parameter) => <label key={parameter.name}>
          <span>{parameter.name}{parameter.default === null ? " *" : ""}</span>
          <Input autoFocus={template.params[0] === parameter} value={values[parameter.name] ?? ""} placeholder={parameter.default === null ? t("required") : `${t("default")}: ${parameter.default}`} onChange={(event) => setValues((current) => ({ ...current, [parameter.name]: event.target.value }))} />
          {parameter.doc && <small>{parameter.doc}</small>}
        </label>)}
      </DialogContent>
      <DialogActions><Button onClick={onCancel}>{t("Cancel")}</Button><Button appearance="primary" disabled={missing} onClick={() => onInsert(values)}>{t("Insert")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function CreateScriptDialog({ busy, onCancel, onCreate }: {
  busy: boolean;
  onCancel: () => void;
  onCreate: (className: string, taskName: string, description: string) => void;
}) {
  const [className, setClassName] = useState("");
  const [taskName, setTaskName] = useState("");
  const [description, setDescription] = useState("");
  const validClassName = /^[A-Za-z_][A-Za-z0-9_]*$/.test(className);
  const valid = validClassName && Boolean(taskName.trim());
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog create-script-dialog"><DialogBody>
      <DialogTitle>{t("Create Task")}</DialogTitle>
      <DialogContent>
        <form id="create-script-form" className="script-dialog-content" onSubmit={(event) => { event.preventDefault(); if (valid && !busy) onCreate(className, taskName.trim(), description.trim()); }}>
          <label>{t("Class Name")}<Input autoFocus required value={className} placeholder={t("Class Name (English only)")} onChange={(event) => setClassName(event.target.value)} /></label>
          {className && !validClassName && <small className="script-field-error">{t("Use English letters, numbers, and underscores; do not start with a number.")}</small>}
          <label>{t("Task Name")}<Input required value={taskName} placeholder={t("Task Name")} onChange={(event) => setTaskName(event.target.value)} /></label>
          <label>{t("Description")}<Input value={description} placeholder={t("Description (Optional)")} onChange={(event) => setDescription(event.target.value)} /></label>
        </form>
      </DialogContent>
      <DialogActions><Button disabled={busy} onClick={onCancel}>{t("Cancel")}</Button><Button form="create-script-form" appearance="primary" type="submit" disabled={!valid || busy}>{t("Create")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function ExportScriptDialog({ tasks, manifest, onCancel, onExport }: {
  tasks: string[];
  manifest: Record<string, string>;
  onCancel: () => void;
  onExport: (selected: string[], fileName: string, scriptName: string, version: string) => void;
}) {
  const [selected, setSelected] = useState(tasks);
  const [fileName, setFileName] = useState(manifest.file_name || "tasks");
  const [scriptName, setScriptName] = useState(manifest.script_name || "");
  const [version, setVersion] = useState(manifest.version || "1.0.0");
  const valid = selected.length > 0 && /^[A-Za-z0-9_.-]+$/.test(fileName) && Boolean(scriptName.trim());
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog"><DialogBody>
      <DialogTitle>{t("Export Script")}</DialogTitle>
      <DialogContent className="script-dialog-content">
        <strong>{t("Select tasks to export:")}</strong>
        <div className="script-export-tasks">{tasks.map((task) => <Checkbox key={task} checked={selected.includes(task)} label={task.replace(/\.py$/, "")} onChange={(_event, data) => setSelected((current) => data.checked ? [...current, task] : current.filter((item) => item !== task))} />)}</div>
        <label>{t("File Name:")}<Input value={fileName} onChange={(event) => setFileName(event.target.value)} /></label>
        <label>{t("Script Name:")}<Input value={scriptName} onChange={(event) => setScriptName(event.target.value)} /></label>
        <label>{t("Version:")}<Input value={version} onChange={(event) => setVersion(event.target.value)} /></label>
      </DialogContent>
      <DialogActions><Button onClick={onCancel}>{t("Cancel")}</Button><Button appearance="primary" disabled={!valid} onClick={() => onExport(selected, fileName, scriptName.trim(), version)}>{t("Export")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function ImportScriptDialog({ file, onCancel, onImport }: { file: File; onCancel: () => void; onImport: () => void }) {
  const [seconds, setSeconds] = useState(15);
  const [accepted, setAccepted] = useState(false);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog"><DialogBody>
      <DialogTitle>{t("Warning")}</DialogTitle>
      <DialogContent className="script-dialog-content">
        <strong>{file.name}</strong>
        <p className="script-import-warning">{t("Make sure that you trust the script publisher. Unverified scripts can steal accounts or data, destroy data, or control your computer.")}</p>
        <Checkbox checked={accepted} onChange={(_event, data) => setAccepted(Boolean(data.checked))} label={t("I understand the risks and want to import this script.")} />
      </DialogContent>
      <DialogActions><Button onClick={onCancel}>{t("Cancel")}</Button><Button appearance="primary" disabled={!accepted || seconds > 0} onClick={onImport}>{seconds > 0 ? `${t("Confirm")} (${seconds})` : t("Confirm")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}

export function RecordScriptDialog({ onCancel, onRecord }: { onCancel: () => void; onRecord: (loop: "none" | "count" | "forever", count: number) => void }) {
  const [loop, setLoop] = useState<"none" | "count" | "forever">("none");
  const [count, setCount] = useState(10);
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => !data.open && onCancel()}>
    <DialogSurface className="script-action-dialog"><DialogBody>
      <DialogTitle>{t("Record")}</DialogTitle>
      <DialogContent className="script-dialog-content">
        <p>{t("Record will override the current script logic. Continue?")}</p>
        <label>{t("Loop")}<select value={loop} onChange={(event) => setLoop(event.target.value as typeof loop)}><option value="none">{t("No loop")}</option><option value="count">{t("Loop x times")}</option><option value="forever">{t("Loop infinitely")}</option></select></label>
        {loop === "count" && <label>{t("Count")}<input type="number" min="1" max="999999" value={count} onChange={(event) => setCount(Math.max(1, Number(event.target.value) || 1))} /></label>}
      </DialogContent>
      <DialogActions><Button onClick={onCancel}>{t("Cancel")}</Button><Button appearance="primary" onClick={() => onRecord(loop, count)}>{t("OK")}</Button></DialogActions>
    </DialogBody></DialogSurface>
  </Dialog>;
}
