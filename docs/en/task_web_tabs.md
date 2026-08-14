# Task-backed custom web tabs

Applications can add browser pages without importing FastAPI or accessing a
`TaskExecutor`. The public API separates backend behavior from presentation:

- `WebCustomTab` is the Python backend and participates in the task lifecycle.
- `WebTabConfig` declares navigation and frontend asset metadata.
- `task_tab_query` and `task_tab_action` explicitly expose allowed operations.

Qt and web configuration are independent. `custom_tabs` is Qt-only;
`web_tabs` is web-only.

## Define the backend

```python
from pathlib import Path

from ok import WebCustomTab, WebTabConfig, task_tab_action, task_tab_query


class ExampleWebTab(WebCustomTab):
    web_tab = WebTabConfig(
        id="example",
        name="Example",
        asset_dir=Path(__file__).with_name("example_web"),
        icon="code",
        task_controls=False,
    )

    @task_tab_query("state")
    def state(self):
        return {"message": "Hello"}

    @task_tab_action("save")
    def save(self, payload):
        value = str(payload.get("value", ""))
        self.emit_web_event("saved", {"value": value})
        return {"value": value}
```

A decorated operation accepts either no arguments or one dictionary payload.
Names must start with a lowercase letter and contain only lowercase letters,
digits, `_`, or `-`. Results and event payloads must be JSON-serializable.
Undecorated methods cannot be called by the browser.

`WebCustomTab` also provides normal task facilities such as `self.config`,
logging, translation, `get_tasks()`, and `emit_web_event()`. It is hidden from
the standard task list and cannot be scheduled.

## Register the page

```python
config = {
    "web_tabs": [["src.ui.ExampleWebTab", "ExampleWebTab"]],
}
```

Every `web_tabs` entry must extend `WebCustomTab`. Entries load only when the
selected UI is web. An application supporting both frontends configures them
separately:

```python
config = {
    "custom_tabs": [["src.gui.ExampleTab", "ExampleTab"]],  # Qt only
    "web_tabs": [["src.ui.ExampleWebTab", "ExampleWebTab"]],  # web only
}
```

## `WebTabConfig`

| Field | Meaning |
| --- | --- |
| `id` | Stable URL-safe identifier using lowercase letters, digits, and single hyphens. |
| `name` | Navigation label, translated by the host when a catalog entry exists. |
| `asset_dir` | Directory containing the browser module and its private static assets. |
| `entrypoint` | ES module loaded by the host; defaults to `index.js`. |
| `icon` | Host icon name such as `code`, `settings`, `image`, `calendar`, or `play`. |
| `position` | `scroll` for primary navigation or `bottom` for fixed bottom navigation. |
| `add_after_default_tabs` | Place a scrolling tab before or immediately after Triggers/Tasks. Defaults to `True`. |
| `task_controls` | Declare that the page uses runnable task controls. Use `False` for management-only `WebCustomTab` pages. |

The asset directory and entrypoint are validated during startup. The
entrypoint cannot escape `asset_dir`.

## Define the browser module

The entrypoint must export `mount(container, context)`. It may return a cleanup
function:

```javascript
export function mount(container, context) {
  container.textContent = context.t("Loading");

  context.query("state").then((state) => {
    container.textContent = state.message;
  });

  const unsubscribe = context.subscribe((event) => {
    if (event.name === "saved") console.log(event.payload);
  });

  return () => unsubscribe();
}
```

The browser context contains:

| API | Purpose |
| --- | --- |
| `tab` | Read-only manifest for the current page. |
| `query(name, payload?)` | Call one `task_tab_query` operation. |
| `action(name, payload?)` | Call one `task_tab_action` operation. |
| `task` | Start, pause, resume, stop, inspect, or configure a runnable owning task. Use only when `task_controls=True`. |
| `subscribe(handler)` | Receive events emitted by this tab; returns an unsubscribe function. |
| `notify(message, intent)` | Show a host notification with `success`, `info`, or `error` intent. |
| `t(message, params?)` | Translate host catalog text. |
| `locale` / `theme` | Current locale and `light` or `dark` theme. |
| `setDirty(boolean)` | Participate in the host's unsaved-change navigation guard. |
| `registerSave(callback)` | Register an async save callback used by the navigation guard. |

Use host CSS variables such as `--accent`, `--card-bg`, `--card-hover`,
`--stroke`, `--selected`, and `--text-muted` so the page follows the active
theme.

## Attach a page to a runnable task

A normal `BaseTask` already registered through `onetime_tasks` or
`trigger_tasks` may declare the same `web_tab = WebTabConfig(...)` metadata.
This is useful when the page is a richer control surface for runnable
automation. Such a task does not also belong in `web_tabs`.

The browser receives neither the executor nor unrestricted Python objects.
Only decorated operations and the bounded task-control interface cross the
HTTP boundary. Keep the server on loopback unless you add authentication and a
trusted reverse proxy.
