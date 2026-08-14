# Runtime architecture

`ok-script` has one framework-neutral runtime and optional UI adapters.

```
ok/core/          events, task discovery, startup, screenshots, downloads, translations
ok/task/          automation task and executor logic
ok/device/        capture and interaction logic
ok/ui/qt/         PySide6 and PySide6-Fluent-Widgets desktop UI
ok/ui/web/        FastAPI API and HTML/JavaScript browser UI
ok/gui/           compatibility namespace for existing imports
```

Core modules publish through `ok.core.events.communicate`. An event signal has a
small `connect`, `disconnect`, and `emit` API without depending on a UI toolkit.
The Qt adapter installs a main-thread dispatcher; the web adapter subscribes to
the same stream and forwards serializable events over a WebSocket.

## Install a mode

```bash
pip install ok-script             # headless core
pip install "ok-script[qt]"       # desktop UI
pip install "ok-script[web]"      # FastAPI/browser UI
```

For repository development, install the TOML dependency group instead. The
`default` group contains the development tools and both UI stacks:

```bash
pip install --editable . --group default
```

## Run a mode

```bash
ok run_task DailyTask --config src.config:config
ok gui --config src.config:config
ok web --config src.config:config --host 127.0.0.1 --port 8000
```

The web server defaults to loopback. Passing a public host such as `0.0.0.0`
exposes task controls to the network, so authentication and a reverse proxy
should be added before doing that on an untrusted network.

The browser UI source is a React + TypeScript + Vite project under the
repository-level `web_src` folder and uses `@fluentui/react-components`.
Only its compiled output is stored under `ok/ui/web/static`, so those runtime
assets are included in the Python wheel. Rebuild them after frontend changes:

```bash
npm install
npm run dev
npm run build
```

Both commands run from the repository root. They regenerate the web translation
catalog from the Qt `.ts` files before starting Vite or producing the packaged
assets.

Application-specific browser pages can be declared by registered tasks without
depending on FastAPI or accessing the executor directly. See
[task-backed web tabs](en/task_web_tabs.md).

New desktop imports should use `ok.ui.qt`. Existing `ok.gui` imports remain
available as a migration shim.
