# Task-backed web tabs

Applications can add browser pages without importing FastAPI or accessing a
`TaskExecutor`. A registered tab declares a `WebTabConfig`, and exposes only
explicitly decorated query and action methods.

Legacy `custom_tabs` is exclusively for Qt and is never imported by the web
adapter. Browser pages use the separate `web_tabs` configuration.

```python
from pathlib import Path

from ok import WebCustomTab, WebTabConfig, task_tab_action, task_tab_query


class ExampleWebTab(WebCustomTab):
    web_tab = WebTabConfig(
        id="example",
        name="Example",
        asset_dir=Path(__file__).with_name("example_web"),
        task_controls=False,
    )

    @task_tab_query("state")
    def state(self):
        return {"message": "Hello"}

    @task_tab_action("save")
    def save(self, payload):
        self.config["Value"] = payload["value"]
        self.emit_web_event("saved", {"value": payload["value"]})
        return self.state()
```

Register a browser-only page explicitly:

```python
"web_tabs": [["src.task.CharacterCodeTask", "CharacterCodeTask"]]
```

Entries must extend `WebCustomTab`. They are loaded only when the selected UI is
web, participate in the normal task lifecycle, and remain hidden from the
standard task list. A normal runnable `BaseTask` already registered through
`onetime_tasks` or `trigger_tasks` can also declare `web_tab` metadata.

An application supporting both interfaces configures them independently:

```python
"custom_tabs": [["src.gui.CharacterCodeTab", "CharacterCodeTab"]],  # Qt only
"web_tabs": [["src.task.CharacterCodeTask", "CharacterCodeTask"]], # web only
```

The `add_after_default_tabs` setting follows Qt ordering: custom tabs appear
before or immediately after the built-in Triggers/Tasks group, while Script,
Templates, Schedule, and configuration pages follow afterward.

The entrypoint defaults to `index.js` and must export a `mount` function:

```javascript
export function mount(container, context) {
  container.textContent = "Loading";
  context.query("state").then((state) => {
    container.textContent = state.message;
  });

  const unsubscribe = context.subscribe((event) => {
    if (event.name === "saved") console.log(event.payload);
  });
  return unsubscribe;
}
```

The browser context provides `query`, `action`, allowlisted task controls,
events, translation, notifications, theme information, and dirty/save page
guards. It intentionally does not expose the executor or unrestricted runtime
objects.
