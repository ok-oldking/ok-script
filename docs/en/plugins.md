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
- **Delete plugin** stages removal for the next launch. Keep persistent user data in the host's configuration/data
  directory, outside the plugin installation.

For example, `https://github.com/hxwd94666/WW-Echo-Workshop` publishes an
`echo-workshop-*.zip` asset containing `echo-workshop/manifest.json`. Both this
single enclosing-folder format and a manifest at the archive root are supported.
Installing an existing ID stages the replacement and displays a restart notice.
The current plugin's files, pages, and tasks remain intact for this session.
First-time installations can load immediately. Downloads and extraction run in the background; task and widget
initialization run on the GUI thread. Packages must supply their dependencies
and native binaries; installation does not run build scripts or pip.

## Applying staged changes

Close and reopen the application to apply a queued update or deletion. Changes
are recorded under `ok_import/.plugin-staging/`, outside the directories scanned
for plugins. **Cancel pending change** discards an unapplied operation while
keeping the current installation. Pending plugins are not checked for updates.

At startup, after checking the application mutex and before discovering plugin
tasks or template assets, the host applies the queued directory changes. An
update's old directory stays available until its tasks and, in desktop mode,
its pages initialize successfully. If initialization fails or that launch exits
before confirmation, the next launch restores the old directory. The manager
reports the failure; cancel it before retrying a different package.

Deletion first moves the installation outside the plugin search path, then
cleans it up. Failed backup/trash cleanup is retried on a later launch and does
not reactivate the removed plugin. Application data outside the plugin directory
is retained. Plugins should still stop their workers and disconnect callbacks
during normal application shutdown.

## GitHub updates

Plugins installed through **Add from GitHub** retain their repository, release
tag, and selected asset across restarts. Each has a **Check for updates** button.
An automatic background check runs 10 seconds after the plugin loads, including
after installation or reload. A busy install delays that check until it finishes.

Release versions must compare strictly greater than the installed manifest's
version (or the saved release tag when the manifest has no version). Numeric
versions and a leading `v` are supported; equal/older versions are not offered.
If versions cannot be compared, the manager displays the check error.

When an update is available, **Update to ...** downloads and stages the chosen
release after the import warning. Restart to activate it. Checks do not install updates automatically.
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
