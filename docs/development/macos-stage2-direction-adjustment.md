# macOS 前台模式阶段 A/B：方向调整与平台安全证据

记录日期：2026-09-04

分支：`feature/macos-foreground-mvp`

状态：**本地无游戏 gate 通过；远端 Windows/macOS runner 尚待本次提交推送后验证**

## 1. 本轮目标

本轮将原 Stage 2 的平台安全安装/导入工作与新的任务能力方向合并：

- relative mouse 不再是整个 Mac 前台 MVP 的统一阻断项；
- 框架提供精确、默认失败关闭的 `DeviceCapabilities`；
- consumer 按任务声明 basic/locked/full-camera 依赖；
- capability 缺失必须在 task enable 或真正执行前失败；
- 继续保持 persistent `SCStream`、foreground-only、`HeldInputState`/`release_all()` 和 Windows 回归边界；
- 不引入 MaaFramework 运行时依赖。

## 2. 当前完成的框架工作

### 2.1 安装与依赖

- 普通 PEP 517/editable build 使用确定性本地 dev version，不再默认查询 PyPI；
- `pywin32`、`pydirectinput`、`pycaw`、`mouse`、`pynput` 和 `ok-d3dshot` 带 Windows marker；
- Darwin 声明 Cocoa、Quartz、ScreenCaptureKit 和 ApplicationServices framework wrappers；
- sibling editable install 在 arm64 Python 3.12 成功；
- `pip check` 成功；
- Mac 环境没有选择上述 Windows-only distribution。

### 2.2 import/provider boundary

- capture、interaction 和 key maps 拆出 common 与 Windows exports；
- `DeviceManager` 仅在 Windows 选择后加载 HWND/WGC/PostMessage；
- Qt start/debug、overlay、notification、process、analytics 等 shared path 在 Darwin 可导入；
- Windows-only feature 在 Mac 明确 unavailable，不通过吞异常伪造成功；
- CursorService 建立平台中立 seam；Mac Quartz 实现仍未开始。

### 2.3 `DeviceCapabilities`

新增字段：

```text
keyboard_tap
keyboard_hold
absolute_mouse
mouse_left
mouse_right
mouse_middle
mouse_button_hold
scroll
relative_mouse
foreground_only
```

契约：

- 默认全部 `False`；
- provider 显式声明；
- `missing()` / `supports()` 可测试；
- inherited empty method 不形成能力；
- `DeviceManager.capabilities` 未就绪时返回全 False；
- `BaseTask.enable()` 前检查；
- `TaskExecutor` 真正运行前再次检查，覆盖排队期间 device/provider 变化；
- consumer 可以只要求 basic/locked 字段，不被 `relative_mouse=False` 误阻断；
- 通用 `TaskCard` 显示 `[experimental]`、`[unsupported]` 或 `[missing: ...]`，并在不兼容时阻止新的 enable；Windows 默认 compatible task 不增加 badge。

## 3. 代码审计结论

OK-WW 当前登记的 17 个 task 已完成静态输入依赖审计。没有登记 task 调用自由 relative/delta camera API。

需要区分：

- `ExecutorOperation.move_relative(x, y)`：把帧百分比转换为绝对坐标移动；
- `BaseWWTask.center_camera()`：屏幕中心中键点击；
- `relative_mouse`：自由镜头 X/Y delta，当前登记 task 未使用。

现有 gameplay 主要依赖：

- `send_key_down` / `send_key_up`；
- W/A/S/D；
- middle button lock/center；
- left/right button hold；
- keyboard/mouse combinations；
- visual target → W/A/S/D direction selection。

因此后续真机输入顺序为：基础 key/mouse → held state → OK-WW combinations → locked task → relative mouse。

## 4. 本地验证

参考环境：Apple Silicon arm64、macOS 15.7.9、Python 3.12.14 arm64。

### 4.1 安装

命令：

```bash
./.venv/bin/python -m pip install --upgrade \
  -e "../ok-script[default,ocr,qt,dev]" \
  -e ".[dev]" \
  opencv-python pytest-subtests
./.venv/bin/python -m pip check
```

结果：

```text
ok-script 2.0.7.dev0 editable
ok-ww 0.0.1 editable
No broken requirements found.
Windows-only distributions selected on Darwin: none
```

### 4.2 capability/import focused tests

从 `ok-script` checkout：

```bash
../ok-wuthering-waves/.venv/bin/python -m pytest -q \
  tests/test_device_capabilities.py \
  tests/test_platform_imports.py
```

结果：通过；Windows-only import case 在 Darwin 按预期 skip。

### 4.3 framework full suite

```bash
QT_QPA_PLATFORM=offscreen \
../ok-wuthering-waves/.venv/bin/python -m pytest -q
```

结果：exit 0。需要 Win32 或 native macOS WindowServer 的测试按明确条件 skip；没有通过删除安全检查或改成空断言获得通过。

### 4.4 OK-WW focused contracts

```bash
./.venv/bin/python -m pytest -q \
  tests/test_macos_capabilities.py \
  tests/test_macos_imports.py \
  tests/TestMouseResetTask.py
```

结果：17 passed（包含全部 17 个登记 task 的 MRO/兼容状态解析）。

OK-WW legacy `Test*.py` 使用独立 Python 进程分三批运行，30/30 文件通过。pytest-style platform tests 不再交给 `unittest` 误判为 “NO TESTS RAN”。

## 5. 尚未验证

### 需要 Windows runner

- WGC/BitBlt/HWND/PostMessage/PyDirect/Pynput 真实平台 import 和 tests；
- Windows dependency resolution；
- 本轮 task preflight 对现有 Windows UI/启动行为的影响；
- legacy Windows workflow 与新 branch guardrail。

### 需要官方《鸣潮》Mac 客户端

- app/window discovery 和真实 bundle identifier；
- Screen Recording / Accessibility；
- persistent `SCStream`；
- 1920×1080 content frame；
- Quartz key/mouse；
- W/A/S/D hold、中键、左右键保持和组合；
- relative mouse；
- 任一 task end-to-end。

### 需要稳定 packaged identity

- `/Applications` 内部 `.app`；
- TCC permission persistence/revoke；
- packaged shutdown release；
- Developer ID/notarization（公开发布阶段）。

## 6. 状态边界

可以标为 `unit-tested`：

- deterministic editable build；
- Darwin dependency marker；
- shared import isolation；
- `DeviceCapabilities` matching/preflight；
- OK-WW 17/17 task declaration；
- `relative_mouse=False` 不阻断 basic/locked requirement；
- task status/missing-capability UI gate；
- `MouseResetTask` Mac P0 明确 unsupported；
- direct Win32 task imports 已移除到 framework service seam。

保持 `not-implemented`：

- `DesktopWindowTarget`；
- permissions；
- `SCStream`；
- geometry generation；
- Quartz interaction；
- `ForegroundGuard`；
- `HeldInputState` / `release_all()`；
- hardware task support；
- packaged app。

## 7. 下一步

进入阶段 C：

1. 定义 `DesktopWindowTarget` 和 immutable geometry snapshot；
2. 添加 Windows adapter tests；
3. 实现 AppKit/ScreenCaptureKit metadata discovery；
4. 实现 manual selection、frontmost observation、activation confirmation 和 rebind；
5. 实现 permission status/request；
6. 建立 stable bundle identifier 的早期 internal `.app` identity checkpoint。

在阶段 C/D/E 完成前，不开始宣称任何游戏 task 可用。
