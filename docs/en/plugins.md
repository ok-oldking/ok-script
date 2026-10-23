# Imported plugins (Qt)

Enable the plugin manager in the host configuration:

```python
config = {
    "plugin": True,
    # other application options...
}
```

`plugin` defaults to `False`. It controls the **Plugins** management tab; existing
packages in `ok_import/` continue to load as before. This manager and custom Qt
pages are desktop-only. Headless and Web runtimes do not instantiate Qt tabs.

## Install and delete

Both add buttons show the same publisher warning as script imports. Installation
requires acknowledging the checkbox and waiting for the 15-second countdown.

- **Add from ZIP** accepts local `.zip` and `.okscript` packages.
- **Add from GitHub** accepts `https://github.com/owner/repository` or
  `owner/repository`. It finds uploaded `.zip`/`.okscript` assets in the latest
  eligible stable release among the twenty most recent releases, falling back
  to a prerelease if there is no eligible stable release. Select the plugin
  package when several assets are available. GitHub's generated source-code
  archives are not selected automatically.
- **Delete plugin** closes its pages and tasks, then removes its installation
  from `ok_import/`. Keep persistent user data in the host's configuration/data
  directory, outside the plugin installation.

For example, `https://github.com/hxwd94666/WW-Echo-Workshop` publishes an
`echo-workshop-*.zip` asset containing `echo-workshop/manifest.json`. Both this
single enclosing-folder format and a manifest at the archive root are supported.
Installing an existing ID replaces that plugin after closing its old pages and
task services. Downloads and extraction run in the background; task and widget
initialization run on the GUI thread. Packages must supply their dependencies
and native binaries; installation does not run build scripts or pip.

## GitHub updates

Plugins installed through **Add from GitHub** retain their repository, release
tag, and selected asset across restarts. Each has a **Check for updates** button.
An automatic background check runs 10 seconds after the plugin loads, including
after installation or reload. A busy install delays that check until it finishes.

Release versions must compare strictly greater than the installed manifest's
version (or the saved release tag when the manifest has no version). Numeric
versions and a leading `v` are supported; equal/older versions are not offered.
If versions cannot be compared, the manager displays the check error.

When an update is available, **Update to ...** downloads and installs the chosen
release after the import warning. Checks do not install updates automatically.
Update archives must match the installed plugin ID and contain a newer version.
Local installations have no GitHub check button. Plugins installed before source
tracking need to be added once through GitHub to enable update checks.

## Tasks and custom tabs

A plugin can declare tasks, custom Qt tabs, or both in `manifest.json`:

```json
{
  "file_name": "my-plugin",
  "script_name": "My plugin",
  "version": "1.0.0",
  "tasks": [["plugin_tasks", "MyTask"]],
  "custom_tabs": [["plugin_page", "MyTab"]]
}
```

Entry points use `[module, class_name]`, relative to the plugin folder. Nested
modules such as `ui.main` are allowed. Task classes extend `BaseTask` or
`TriggerTask`. Both kinds appear in the standard task tab; declared custom tabs
receive their own navigation entries.

If `tasks` is omitted, the legacy loader discovers task classes in root `.py`
files. Set `"tasks": []` for a tab-only plugin. `custom_tabs` defaults to `[]`.
Declared tab modules are imported only by the Qt adapter.

```python
# plugin_page.py
from qfluentwidgets import BodyLabel, FluentIcon
from ok.ui.qt.widget.CustomTab import CustomTab


class MyTab(CustomTab):
    icon = FluentIcon.APPLICATION

    @property
    def name(self):
        return "My plugin"

    def __init__(self):
        super().__init__()
        self.add_widget(BodyLabel("Plugin content", self.view))

    def dispose(self):
        # Disconnect plugin subscriptions and stop page-owned workers here.
        pass
```

The host assigns `tab.executor` after construction, as with configured host
custom tabs. It owns navigation and widget destruction. Pages may expose
`dispose()` (or `stop_worker()`) for cleanup. Imported tasks receive
`on_destroy()` when unloaded. Task-code reload replaces the whole plugin so
pages cannot retain old task instances. One failing tab is logged and displayed
in the manager without preventing the other tabs from loading.

## Existing task-owned pages

For packages such as Workshop, an imported task can instead expose
`create_import_page(parent)` and return an embedded `QWidget`. With no explicit
`custom_tabs` declaration, these pages replace the generic task-card tab. Tasks
remain registered and runnable. If page creation fails, the host retains the
standard task-card interface.

This needs no `on_main_window()` callback, host monkey patch, or application
`custom_tabs` configuration. Keep Qt page imports inside the factory so task
definitions remain usable by headless runtimes.
