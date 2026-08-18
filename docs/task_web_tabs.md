# 基于任务 API 的 Web 自定义页

应用可以添加浏览器页面，而不需要导入 FastAPI，也不能直接访问
`TaskExecutor`。公开 API 将后端行为与界面元数据分开：

- `WebCustomTab` 是 Python 后端，使用正常的任务生命周期和任务 API。
- `WebTabConfig` 描述导航位置和前端资源。
- `task_tab_query` 与 `task_tab_action` 明确声明浏览器可以调用的方法。

Qt 与 Web 使用独立配置：`custom_tabs` 只属于 Qt，`web_tabs` 只属于
Web。

## 定义后端

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

公开的方法只能不接收参数，或接收一个字典参数。操作名必须以小写字母
开头，并且只能包含小写字母、数字、`_` 或 `-`。返回值和事件数据必须
可以序列化为 JSON。未添加装饰器的方法无法从浏览器调用。

`WebCustomTab` 还可以使用 `self.config`、日志、翻译、`get_tasks()` 和
`emit_web_event()` 等任务 API。它不会显示在普通任务列表中，也不能被
计划任务调度。

## 注册页面

```python
config = {
    "web_tabs": [["src.ui.ExampleWebTab", "ExampleWebTab"]],
}
```

`web_tabs` 中的类必须继承 `WebCustomTab`，并且只会在 Web UI 模式下
加载。同时支持 Qt 和 Web 时应分别配置：

```python
config = {
    "custom_tabs": [["src.gui.ExampleTab", "ExampleTab"]],  # 仅 Qt
    "web_tabs": [["src.ui.ExampleWebTab", "ExampleWebTab"]],  # 仅 Web
}
```

## `WebTabConfig` 字段

| 字段 | 作用 |
| --- | --- |
| `id` | 稳定的 URL 标识，只能使用小写字母、数字和单个连字符。 |
| `name` | 左侧导航名称；翻译目录存在对应文本时由宿主翻译。 |
| `asset_dir` | 浏览器模块及其私有静态资源所在目录。 |
| `entrypoint` | 宿主加载的 ES 模块，默认为 `index.js`。 |
| `icon` | 宿主图标名，例如 `code`、`settings`、`image`、`calendar` 或 `play`。 |
| `position` | `scroll` 表示主导航，`bottom` 表示固定在导航底部。 |
| `add_after_default_tabs` | 放在 Triggers/Tasks 之前或紧接其后，默认为 `True`。 |
| `task_controls` | 页面是否使用可运行任务控制；纯管理页面应设为 `False`。 |

启动时会验证资源目录和入口文件，入口文件不能跳出 `asset_dir`。

## 定义浏览器模块

入口模块必须导出 `mount(container, context)`，并且可以返回清理函数：

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

`context` 提供以下接口：

| API | 作用 |
| --- | --- |
| `tab` | 当前页面的只读清单。 |
| `query(name, payload?)` | 调用一个 `task_tab_query`。 |
| `action(name, payload?)` | 调用一个 `task_tab_action`。 |
| `task` | 启动、暂停、继续、停止、读取或配置可运行任务；仅在 `task_controls=True` 时使用。 |
| `subscribe(handler)` | 接收当前页面的事件，并返回取消订阅函数。 |
| `notify(message, intent)` | 显示 `success`、`info` 或 `error` 通知。 |
| `t(message, params?)` | 翻译宿主目录中的文本。 |
| `locale` / `theme` | 当前语言和 `light`/`dark` 主题。 |
| `setDirty(boolean)` | 接入宿主的未保存修改导航保护。 |
| `registerSave(callback)` | 注册导航保护使用的异步保存函数。 |

页面应使用 `--accent`、`--card-bg`、`--card-hover`、`--stroke`、
`--selected` 和 `--text-muted` 等宿主 CSS 变量适配主题。

普通的 `BaseTask` 如果已经通过 `onetime_tasks` 或 `trigger_tasks` 注册，
也可以声明 `web_tab = WebTabConfig(...)`，为可运行任务提供自定义控制页。
这种任务不需要再次添加到 `web_tabs`。

浏览器不会获得 executor 或任意 Python 对象。只有显式装饰的方法和受限
任务控制接口可以通过 HTTP 调用。除非已经添加认证和可信反向代理，否则
Web 服务应只监听本机地址。
