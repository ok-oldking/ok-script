# macOS 前台模式 Stage C：窗口目标与权限状态

记录日期：2026-09-04

分支：`feature/macos-foreground-mvp`

状态：**本地无游戏 contract tests 通过；远端 runner、真实官方客户端和 packaged `.app` 待验收**

## 1. 本阶段边界

本阶段仅建立：

- 平台中立 `DesktopWindowTarget`、不可变 snapshot 与 binding/geometry `generation`；
- 通过 composition 包装现有 `HwndWindow` 的 Windows adapter；
- 基于公开 AppKit、ScreenCaptureKit metadata 与 Quartz window list 的 macOS discovery/target adapter；
- app identity、标题辅助、layer、尺寸和显式手选组成的候选选择；
- PID/window ID 存活、前台观察、activation request 与 observed activation 分离；
- Screen Recording 与 Accessibility 的 preflight/request/status service；
- `DeviceManager` 中不提供 capture/input 的 macOS target-only 分支。

本阶段没有加入 persistent `SCStream`、capture frame、坐标转换、Quartz input、relative mouse、任务开放或后台控制。

## 2. Fail-closed 语义

- title-only hint 永不自动绑定；唯一 app identity 候选可忽略其他无关 eligible 窗口自动绑定，同一稳定 app identity 出现多个窗口时要求显式选择；
- 持久化 hint 只包含 bundle identifier、application name 和辅助 title，不包含 PID、window ID、geometry 或 generation；
- `bind()` 低频重新枚举并按 PID/window ID 找到当前候选，再验证进程和 Quartz window ID/owner PID；绑定对象使用二次枚举的 metadata，避免沿用选择界面的旧 geometry/title；
- `exists()` 同时检查进程与 Quartz window ID/owner PID；
- refresh 开始时 target 内部立即清空 candidate 并提升 generation；即使同一窗口成功恢复也保留新 generation，确保刷新前的帧和坐标全部失效；
- refresh 异常、窗口消失或歧义重绑会清空旧 candidate、PID 和 geometry；
- activation API 返回值只表示请求被接受，调用方仍必须观察实际 frontmost；
- permission 的 check-and-request 由可重入锁串行化；进入 `permission-requested` 后 `can_request=False`，避免并发或紧密循环重复弹窗；观察到 granted 后清除 requested，后续 revoke 可再次显式请求；
- macOS target 在 Stage C 始终 `connected=False`，可用 capture/interaction 列表为空，不会落入 ADB provider。

## 3. 坐标与诊断边界

`SCWindow.frame` 只记录为 `macos-global-logical-points` 的 outer geometry。`content_geometry`、`capture_geometry` 和 `display_scale` 继续为 unknown，必须由 Stage D 的真实 `SCStream` frame 和坐标模型建立，不能从 outer frame 推断。

诊断可输出 PID、bundle identifier、application name、window ID、title、layer、outer geometry coordinate space 和实时 frontmost metadata。它不启动截图或输入。

## 4. 本地自动化证据

参考解释器：OK-WW sibling `.venv` 的 Python 3.12 arm64。

```bash
../ok-wuthering-waves/.venv/bin/python -m pytest \
  tests/test_window_target.py \
  tests/test_macos_window_target.py \
  tests/test_permissions.py \
  tests/test_device_manager.py \
  tests/test_platform_imports.py \
  tests/test_runtime_startup.py
```

结果：`55 passed, 1 skipped`；skip 为当前 Darwin 上的 Windows-only import isolation case。

```bash
../ok-wuthering-waves/.venv/bin/python -m mypy \
  --follow-imports=skip --ignore-missing-imports \
  ok/device/window_target \
  ok/device/services/permissions.py \
  ok/device/services/macos_permissions.py
```

结果：`Success: no issues found in 8 source files`。

```bash
../ok-wuthering-waves/.venv/bin/python -m pytest
```

沙箱内 8 个 web tests 因禁止绑定 `127.0.0.1` 返回 `PermissionError`；在允许 loopback 的执行边界外复跑同一命令后，结果为 `336 passed, 12 skipped, 4 subtests passed`。该环境性失败没有通过修改或跳过测试规避。

## 5. 仍未验证

- 本机未安装可识别的官方《鸣潮》Mac 客户端，因此没有真实 bundle identifier、application name、窗口候选或 window replacement 证据；
- 当前 source identity 的 Screen Recording 与 Accessibility preflight 均为 `permission-required`，未请求权限；
- Command-Tab、真实 activation、进程退出和窗口重建待官方客户端硬件验收；
- stable bundle identifier 的内部 `.app` 尚未实现，TCC persistence/revoke 待 packaged identity 验收；
- Stage D/E 之前没有 capture/input capability，不能执行任何 Mac task。

## 6. 下一门槛

Stage C 提交后先通过两仓库 macOS/Windows CI，并在具备官方客户端时补真实窗口/权限记录。Stage D 才开始 persistent `SCStream`、实际帧与 geometry generation 集成。
