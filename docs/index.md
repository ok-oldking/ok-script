---
hide:
  - navigation
  - toc
---

<div class="ok-hero" markdown>

# Vibe Coding 自动化框架

**在 Codex、Claude Code 或任何支持 MCP 的编程代理里许个愿，得到一个可部署的自动化程序。**

代理通过 MCP 观察 Windows 应用、游戏或安卓设备，编写 Python 任务，在真实目标上运行并修复失败。ok-script 把完成的任务连同桌面 GUI 打包成可分发的 Windows 安装包。打包后的程序独立运行，无需代理保持连接。

[MCP 快速开始](quick_start/README.md){ .md-button .md-button--primary }
[复制代理提示词](agent-prompts.md){ .md-button }
[English](en/index.md){ .md-button }

</div>

## MCP 开发流程

代理用自己的工具编辑文件、读取日志；MCP 让它直接操作正在运行的应用。

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } __1. 学习__

    ---

    `list_skills` 和 `get_skill` 返回当前安装版本自带的开发、模板、测试和重载流程；代理从已安装包中读取准确的 Python 签名。

-   :material-monitor-screenshot:{ .lg .middle } __2. 观察__

    ---

    `screenshot` 保存已配置窗口或设备的当前画面，代理看到的就是任务将要看到的。

-   :material-play-circle:{ .lg .middle } __3. 运行__

    ---

    `run_task` 在真实目标上执行 Python 任务文件。每次尝试先恢复并验证起始状态，再由 `run()` 执行并断言自动化结果。

-   :material-file-search:{ .lg .middle } __4. 检查__

    ---

    每次尝试在 `logs/mcp/<run_id>/` 下写入 `run.log`、`status.json` 和任务截图。`get_run_status` 报告进度和错误，`stop_task` 用于取消。

-   :material-wrench:{ .lg .middle } __5. 修复__

    ---

    `list_tasks` 返回已注册任务的源码路径；修改后用 `reload_tasks` 在运行中的进程里替换。无法重置时用 `exit_process` 结束运行时。

-   :material-rocket-launch:{ .lg .middle } __6. 交付__

    ---

    注册任务，通过 GUI 或 `python -m ok run_task` 运行，并用 [PyAppify](https://github.com/ok-oldking/pyappify) 打包成 Windows 安装包。详见[打包与发布](after_quick_start/README.md)。

</div>

## 可以这样告诉编程代理

=== "开发任务"

    > 连接这个项目的 ok-script MCP 服务，读取开发技能。检查已安装的截图、匹配和输入 API，给出准确签名和源码位置。开发可复用 Python 任务：打开设置、启用“显示详情”、保存并验证结果。每次尝试前恢复并验证起始界面，测试重复运行，代码保存到项目中。使用 ok-script API 和 MCP，不使用 Computer Use 工具。最后给出不依赖代理或大模型调用的准确运行命令。

=== "修复任务"

    > 连接这个项目的 ok-script MCP 服务，读取 reload-tasks 技能。用 list_tasks 找到出错任务的源码，修改该文件，按任务 ID 重载并等待重载成功。恢复并验证起始界面，重复运行已注册的实现，并给出运行日志和截图中的证据。

=== "安装环境"

    > 在当前项目中安装 ok-script 并配置运行环境。先读取 https://raw.githubusercontent.com/ok-oldking/ok-script/master/docs/agent-setup.md ，按照其中的安装技能操作，保留项目现有的依赖约束。

[编程代理提示词](agent-prompts.md)提供了查询 API、开发任务和维护已有任务的完整示例。

## 三步连接

```powershell
.\.venv\Scripts\python.exe -m pip install "ok-script[default]"
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

1. 用项目配置启动运行时，或在已有桌面应用中开启 **设置 > 基本设置 > 启用 MCP 服务器**。
2. 从有效的 `logs/mcp/connections/<pid>-<port>.json` 记录中读取 URL 和 token。
3. 让代理的 MCP 客户端通过 Streamable HTTP 连接，并使用 `Authorization: Bearer <token>` 请求头。

!!! warning "本地开发者权限"
    服务只监听本机回环地址，但已连接的代理可以用你的账户权限执行 Python。不要公开 token，日常使用请保留单独的、关闭 MCP 的启动器。

## 文档导航

<div class="grid cards" markdown>

-   :material-flag-checkered:{ .lg .middle } __开始 MCP 开发__

    ---

    [MCP 快速开始](quick_start/README.md) · [代理安装指南（英文）](agent-setup.md) · [编程代理提示词](agent-prompts.md)

-   :material-api:{ .lg .middle } __MCP 参考__

    ---

    [MCP 连接与执行（英文）](mcp.md)：工具、运行状态、重载、诊断和任务文件约定。[模板导出格式（英文）](feature-crops.md)。

-   :material-package-variant-closed:{ .lg .middle } __交付与维护__

    ---

    [维护和分享任务](after_quick_start/README.md)：模板、回归测试、国际化和打包。[导入插件](plugins.md) · [Windows 计划任务](Windows%20计划任务.md)

-   :material-cog-outline:{ .lg .middle } __原理与工具__

    ---

    [自动化原理](intro_to_automation/README.md) · [界面与开发工具](interface.md) · [运行时架构（英文）](architecture.md)

</div>

需要具体 API 时，让代理检查项目实际安装版本的源码和方法签名，无需手动查阅静态 API 手册。
