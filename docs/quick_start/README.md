# MCP 快速开始

[English](../en/quick_start.md) · [文档中心](../index.md) · [编程代理提示词](../agent-prompts.md)

用编程代理开发自动化，保存 Python 任务后重复运行。你需要 Windows、Python 3.11 或更高版本、目标应用或 ADB 设备，以及支持 MCP 和本地文件、进程访问的编程代理。

## 1. 打开应用项目

使用已有的 ok-script 应用，或从 [ok-script-app 模板](https://github.com/ok-oldking/ok-script-app)创建项目。在编程代理中打开应用目录。业务任务保存在这个项目里，与 ok-script 框架仓库分开。

可以这样告诉代理：

> 准备这个自动化项目的虚拟环境和依赖，保留现有依赖约束和 ok-script 版本。配置我的目标应用，分别提供 MCP 开发入口和用户 GUI 入口。有可用技能时读取 setup-env 和 setup-project。不要使用 Computer Use 工具。

新建环境的基本命令：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "ok-script[default]"
```

已有应用先安装自己的依赖。MCP 自 2.0.17 起为必需依赖，随 ok-script 自动安装。按需添加 `qt`、`adb` 或 `ocr`。OpenCV 需要单独安装，且只能选择一个兼容变体，例如 `opencv-python` 或 `opencv-python-headless`；让代理沿用项目现有选择。

项目还需要配置真实目标。让代理检查已安装版本的配置实现及已有示例，设置应用可执行文件、窗口或 ADB 包名，并验证截图和输入。安装包本身不会自动创建已配置的应用。

## 2. 启动 MCP 运行时

优先使用项目已有的开发入口。否则，在应用目录执行：

```powershell
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

将 `src.config:config` 替换为实际配置模块和对象。开发期间保持进程运行。该模式不需要 Qt，普通任务调度器保持暂停。

已有桌面应用也可在**设置 > 基础选项 > 启用 MCP 服务**中开启。开启前阅读应用显示的访问提示。日常使用应保留独立的、禁用 MCP 的 GUI 入口。

## 3. 连接编程代理

从项目配置的产物目录读取 `logs/mcp/connections/<pid>-<port>.json` 中的有效记录，其中包含服务 URL、bearer token、进程身份和项目目录。默认端口为 8765，但可能变化，不要写死。

代理 MCP 客户端使用以下连接信息：

| 设置 | 值 |
| --- | --- |
| 传输 | Streamable HTTP |
| URL | 有效连接记录中的 `url` |
| HTTP 请求头 | `Authorization: Bearer <有效记录中的 token>` |

各客户端配置格式不同，让代理按它支持的方式配置并保管 token。服务只监听本机回环地址，因此代理应运行在同一台机器上，并能访问项目文件。没有原生 MCP 连接能力时，可让代理用官方 MCP Python SDK 编写本地客户端。

让代理调用 `list_skills()`、读取 `get_skill("develop")`，再用 `screenshot()` 确认目标。如果截图错误或无法截图，先修复配置再执行任务。详见 [MCP 连接说明（英文）](../mcp.md)。

## 4. 提出可复用任务需求

> 使用这个项目的 MCP 连接，开发可复用 Python 任务：打开设置、启用“显示详情”、保存，并验证该选项保持开启。先读相关技能并核实已安装 API 的签名。代码保存在正式任务模块里；每次 MCP 尝试前恢复并验证起始状态，记录日志和截图，断言可见结果，并验证重复运行。使用 ok-script 截图和输入，不使用 Computer Use。注册任务，使其无需代理或大模型调用即可运行。

代理在本地编写文件，并将绝对路径提交给 MCP。修改已有任务时，先发现原始源码、原地编辑、重载已注册任务，等待重载成功后再测试。查询 API 和维护任务的完整示例见[提示词指南](../agent-prompts.md)。

## 5. 脱离代理运行

让代理给出项目真实任务名和入口。保存的任务必须已注册，并在普通运行时自行准备状态；GUI/CLI 不会自动调用 MCP 的恢复钩子。

普通 CLI 运行前，停止 MCP 开发运行时并等待退出。同一项目启动 GUI 会替换已注册的控制台运行时并关闭它的 MCP 连接。不要在任务尝试尚未结束时切换模式。典型命令如下：

```powershell
.\.venv\Scripts\python.exe -m ok run_task EnableOptionTask --config src.config:config
.\.venv\Scripts\python.exe -m ok gui --config src.config:config
```

选择 CLI 或 GUI 其中一种运行，不要同时启动。CLI 参数是已注册任务名或类名，不是 Python 文件路径。日常 GUI 使用优先选择应用提供的、禁用 MCP 的 `pythonw.exe` 入口或快捷方式；GUI 需要 Qt 依赖。

将任务源码、配置、识别素材和依赖约束一起保存。本地 Python 识别与输入在日常运行时不消耗模型 Token；新增需求或需要修复时再找编程代理。
