# macOS 前台模式 Stage D：ScreenCaptureKit 持久流与几何

记录日期：2026-09-04

分支：`feature/macos-foreground-mvp`

状态：**本地自动化、官方客户端窗口模式 1920×1080/1000 帧与临时标准窗口 move/resize source-identity 验收通过；远端 CI 和 packaged `.app` 待验收**

## 1. 本阶段边界

本阶段仅加入：

- `SCContentFilter(desktopIndependentWindow:)`、显式 `SCStreamConfiguration` 和一个持久 `SCStream`；
- `CMSampleBuffer` callback 内的完整帧筛选、BGRA/stride/padding 处理和 owned BGR copy；
- 单槽 latest-frame publication；
- target generation 与独立 capture generation 绑定的 immutable frame packet；
- resize、scale、content rect 或 target rebind 变化时的旧帧失效和流重建；
- consumer 读取时重新验证目标存活；native stop 未确认时进入 fatal，禁止并行启动替代 stream；
- FPS、frame age、overwrite、drop、generation、geometry invalidation 和 rebuild 诊断；
- 帧物理像素到 macOS 全局逻辑点的通用 geometry mapping；
- 通过公开 Accessibility AXWindow metadata 与 AppKit 标准窗口几何建立客户区 `sourceRect`；无法唯一确认客户区时失败关闭；
- 使用同一 `displayID` 对应的公开 `NSScreen.backingScaleFactor` 配置 HiDPI 输出，不把单位同为 points 的 `SCDisplay.width/height` 与 `SCDisplay.frame` 相除；
- 使用公开 `SCStreamFrameInfoScreenRect` 观察窗口移动/resize，变化时立即丢弃旧几何、refresh target 并重建 stream；
- `DeviceManager` 的 macOS capture provider 路由。

本阶段没有加入 Quartz 输入、`ForegroundGuard`、`HeldInputState`、`release_all()`、relative mouse、任务开放、后台控制或任何 TCC 绕过。

## 2. 生产路径和所有权

```text
SCShareableContent（仅 source resolve/rebind）
  → selected SCWindow
  → SCContentFilter(desktopIndependentWindow:)
  → one SCStreamConfiguration
  → persistent SCStream
  → CMSampleBuffer callback
  → owned BGR ndarray + immutable CaptureGeometry
  → one-slot LatestFrameSlot
```

配置显式使用 BGRA、`showsCursor=False`、`queueDepth=3`、30 FPS、no audio，并在可用系统上设置 `ignoreShadowsSingleWindow=True`。输出尺寸配置只用于请求接近原生 display scale 的 surface；视觉尺寸和 stride 始终以实际 `CVPixelBuffer` 为事实来源。

PyObjC 的 `CVPixelBufferGetBaseAddress()` 作为 `objc.varlist` 处理，在 lock 期间通过 `as_buffer(bytes_per_row * height)` 建立有界 view。BGR 数组在 unlock 前完成连续 owned copy，不依赖 IOSurface callback 生命周期。

## 3. Fail-closed generation 语义

- 每个 callback 捕获不可变 target generation 和 capture generation；发布前后均重新检查当前 target/state/generation；
- target refresh/rebind 开始前先提升 capture generation、清空 latest slot，并阻止旧 target generation 重启；
- actual frame size、content rect、display scale 或 content scale 改变时，当前 generation 立即失效，下一次 consumer poll 重建 stream；
- permission missing/revoked、target lost、fatal stream stop 和 close 均清空 slot；
- fatal start/stop 在同一 target generation 上不会 tight retry；
- native stop 超时或失败后保留未确认 binding 到 close，并保持 fatal；不会启动第二个 stream；
- target 的实时 liveness 检查失败或返回 lost 时停止 stream、清空 slot，不能由旧 snapshot 继续返回帧；
- start/rebuild race 进入 fatal 后不能被并发同步路径重置为 running；fatal start 会清空 callback 可能提前发布的帧和几何；
- conversion failure 不返回此前的旧帧；
- `interaction` 和 device capabilities 继续为空，因此 Stage D capture 就绪不等于任何 Mac task 可执行。

## 4. 几何边界

`CaptureGeometry` 同时记录 outer global logical geometry、global content geometry、raw surface pixels、content rect pixels、normalized frame pixels、display scale、target generation 和 capture generation。

`SCStreamFrameInfoContentRect` 按 Apple API 定义视为 surface points，并使用 `SCStreamFrameInfoScaleFactor` 转成物理像素 crop。标准窗口客户区先通过 AXWindow 身份和 AppKit `contentRectForFrameRect:styleMask:` 建立，再传入 `SCStreamConfiguration.sourceRect`。帧坐标映射使用 normalized frame 与 global content geometry 的实际比例，不假设 scale 固定为 2.0。

当前官方客户端窗口模式已证明输出不含标题栏、边框、阴影和光标。窗口逻辑客户区为 `960×540`，`display_scale=2.0`；使用 `NSScreen.backingScaleFactor` 后实际 `CVPixelBuffer` / BGR frame 为 `1920×1080×3 uint8`，`content_scale=1.0`。此前的 `960×540` 回调暴露了 `SCDisplay.width/height` 也是 points 的配置错误，不能作为 Retina 物理输出尺寸来源。视觉任务仍需独立 OCR/template 真机证据，不能仅凭 capture frame 声称受支持。

## 5. 本地自动化证据

参考解释器：OK-WW sibling `.venv` 的 Python 3.12 arm64。

```bash
../ok-wuthering-waves/.venv/bin/python -m pytest \
  tests/test_screencapturekit_core.py \
  tests/test_screencapturekit_capture.py \
  tests/test_macos_window_target.py \
  tests/test_permissions.py \
  tests/test_device_manager.py \
  tests/test_platform_imports.py
```

新增真实 CGRect dictionary bridge、automatic-resolution availability、AX 标准窗口客户区、`NSScreen.backingScaleFactor`、`SCStreamFrameInfoScreenRect`、global content geometry 与 fail-closed regression tests 后，定向结果为 `74 passed, 1 skipped`；skip 为当前 Darwin 上的 Windows-only import isolation case。

```bash
../ok-wuthering-waves/.venv/bin/python -m mypy \
  --follow-imports=skip --ignore-missing-imports \
  ok/device/capture_methods/screencapturekit_core.py \
  ok/device/capture_methods/screencapturekit.py
```

结果：`Success: no issues found in 2 source files`。

```bash
../ok-wuthering-waves/.venv/bin/python -m pytest -q
```

结果：`375 passed, 12 skipped, 4 subtests passed`。skip 均为既有平台/UI/runtime 条件，其中一个 web test 因当前环境未安装可选 `httpx2`。

另外在当前 Darwin/PyObjC runtime 完成了无捕获 smoke：`SCStreamConfiguration` 的 width/height/BGRA/queueDepth/showsCursor setter、serial dispatch queue，以及 `SCStreamOutput`/`SCStreamDelegate` protocol callback signature 均可构造。

## 6. 官方客户端 source-identity 硬件证据

环境为 Mac `Mac16,8` / Apple M4 Pro、macOS 15.7.9 (`24G830`)、Python 3.12.14 arm64；官方客户端 `3.6.0` (`CFBundleVersion=176826892`)。游戏窗口位于物理 `3840×2160`、UI logical `1920×1080`、`backingScaleFactor=2.0` 的主显示器；系统另有在线虚拟显示器，但本次捕获未选择或依赖它。

官方客户端窗口模式观测：

- application name：`鸣潮`；bundle identifier：`com.kurogame.mingchao`；
- outer logical geometry：`x=0, y=213, 960×568`；
- AX/AppKit content geometry：`x=0, y=241, 960×540`，标题栏为顶部 28 points；
- actual raw/normalized BGR frame：`1920×1080×3 uint8`；逻辑客户区 `960×540`，`display_scale=2.0`，`content_scale=1.0`；
- 视觉检查确认 color 正确，且无 cursor/title/border/shadow；个人账户内容截图仅用于临时检查，验收后已删除且未提交仓库；
- 最终 1000 unique frames 用时 `34.295 s`，capture FPS `29.243`；received/published `1001`、incomplete/stale/conversion error `0`、storage size `1`、geometry invalidation/rebuild `0`，并确认 `capture.close()` 完成；
- 非零位置临时标准 AppKit 窗口从 `x=300` 移动到 `x=500` 时旧 geometry 立即失效并重建；随后客户区从 `640×360` resize 为 `800×450` 时再次失效并重建，最终输出从 `1280×720` 恢复为 `1600×900`，target generation `1→2→3`、geometry invalidation/rebuild 均为 `2`；
- 全程未发送键盘、鼠标或 activation 输入。

此证据属于已授权 Terminal/Python source identity，不等于 packaged `.app` identity。

## 7. 仍未验证

- 尚未在官方客户端上验证 display migration、window replacement 和 PID change；move/resize 恢复证据来自临时标准 AppKit 窗口；
- `SCStreamFrameInfoScreenRect` 从 macOS 13.1 提供；macOS 13.0 的同尺寸移动检测 fallback 仍需在进入输入阶段前闭合；
- 全屏/无边框不属于本次窗口模式验收；当前生产路径要求可唯一确认的 `AXStandardWindow` 与标准标题栏，否则失败关闭；
- 未建立 packaged `.app` 的稳定 TCC identity 证据；
- Quartz 输入及全部 fail-closed release 语义仍属于 Stage E。
