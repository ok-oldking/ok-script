# ok-script macOS 前台平台层工程约束

状态：**OK-WW macOS 前台模式 MVP 的规范性平台实现约束**

本文约束 `ok-script` 中可复用的平台能力。配套 OK-WW 仓库的 `MACOS_ENGINEERING_CONSTRAINTS.md` 是产品合同；本文件可以细化框架实现，但不得削弱“仅前台、仅公开 API、失败关闭、Windows 不回归”。

## 0. 规范层级与变更

- 运行时代码修改前必须阅读本文件、`AGENTS.md`、Stage 1 inventory、同步/回滚说明和配套 OK-WW 约束。
- 有意偏离前台语义、公开 API 政策、仓库职责、坐标/帧/输入安全契约或 Windows 兼容性时，必须先提交 ADR。
- 聊天、issue、代码注释或 PR 讨论不能代替 ADR。
- 本工作继续保留在长期 `feature/macos-foreground-mvp` 分支；不拆阶段性合并 PR。

## 1. 目标与仓库职责

`ok-script` 必须提供：

- 平台安全的依赖、导入和 provider 路由；
- 平台中立 `DesktopWindowTarget`；
- Windows 现有 HWND 行为的兼容 adapter；
- macOS 应用/窗口枚举、选择、前台观察和重绑；
- Screen Recording 与 Accessibility 权限服务；
- 持久 `ScreenCaptureKitCaptureMethod`；
- `QuartzForegroundInteraction`；
- `ForegroundGuard`；
- `HeldInputState` 与幂等 `release_all()`；
- `CursorService`；
- `DeviceCapabilities`；
- 帧、内容区、显示器和输入坐标转换；
- 可测试的生命周期、错误状态和诊断指标。

《鸣潮》bundle identifier、标题提示、游戏热键、任务兼容性、视觉资源和用户文档属于 OK-WW，不得放入框架。

## 2. 支持基线与禁止范围

框架公开 API 设计与通用 host gate 基线（不是 consumer 二进制发行承诺）：

- Apple Silicon arm64；
- macOS 13+；
- Python 3.12 arm64；
- AppKit、ScreenCaptureKit、Core Graphics / Quartz、ApplicationServices、Foundation / CoreFoundation 等公开 API。

当前首个 consumer OK-WW 的 packaged MVP 发行基线为 Apple Silicon、macOS 15+、Python 3.12 arm64，原因是随包 Python/PySide6 wrapper 的真实 Mach-O 最低版本。用户于 2026-09-06 授权 contributor 分支收窄，见 [ADR 0002](decisions/0002-consumer-packaged-minimum-version.md)；不代表 upstream 接受。框架 host gate 仍为 13+，公开 API 设计继续兼顾 13+；完整依赖组合在 13/14 的兼容性与硬件支持仍须独立证明。不得通过下调 plist、Mach-O 标记或仅设编译环境变量声称支持旧系统。

本 MVP 不实现：

- 后台、最小化或其他 Mission Control Space 自动化；
- BetterDisplay、虚拟显示或私有 `CGVirtualDisplay`；
- `CGEvent.postToPid` 后台输入；
- 进程/dylib 注入、swizzling、Metal hook 或反作弊绕过；
- TCC 数据库修改、root 绕过或自动提权；
- MaaFramework 运行时依赖。

## 3. 依赖和平台安全导入

- `pyproject.toml` 是依赖事实来源。
- `pywin32`、`pydirectinput`、`pycaw`、适用的 `comtypes`、Windows-only `mouse`/`pynput` 和 `ok-d3dshot` 必须带 Windows marker 或进入 Windows extra。
- macOS 只声明实际使用的最小 PyObjC framework wrapper。
- editable/PEP 517 build 必须确定性，不得在普通构建期间隐式查询 PyPI 版本。
- 共享模块顶层不得无条件导入 Win32、`ctypes.windll`、`ctypes.WinDLL`、AppKit、Quartz、ScreenCaptureKit 或 ApplicationServices 实现。
- 必须先选择平台/provider，再导入具体实现。
- 不得用散布式宽泛 `try/except ImportError` 隐藏错误边界。
- Darwin import smoke 必须覆盖 `import ok`、`DeviceManager`、executor、Qt 启动模块和 consumer 全任务导入，且 `sys.modules` 中无 Win32-only backend。
- Windows import/test 不得要求 PyObjC。

## 4. `DeviceCapabilities` 契约

框架提供细粒度、默认失败关闭的能力模型：

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

要求：

- 所有新 interaction provider 默认全部为 `False`；
- 只有实现和安全语义真实存在时才能声明 `True`；
- 继承的空方法、日志 stub 或异常吞掉不能形成能力；
- 任务在 enable 前和真正执行前都必须重新检查要求；
- 能力缺失时在任务逻辑开始前失败，不能运行到中途才发现方法为空；
- `foreground_only=True` 表示每个普通事件/短原子批次前均有 fail-closed 前台校验，不等于“通常在前台运行”；
- `relative_mouse` 专指自由镜头相对/delta 输入，不等于将帧内百分比换算为绝对坐标的 helper。

游戏专属的 `MAC_BASIC`、`MAC_LOCKED_GAMEPLAY`、`MAC_FULL_CAMERA` 分级属于 consumer；框架只实现精确能力和通用匹配。

## 5. `DesktopWindowTarget`

不得把 `HwndWindow` 扩充成带大量 HWND 假设的伪通用类。

平台中立 target 至少表达：

- PID 和进程存活状态；
- 可选 bundle/application identifier；
- 平台 window ID；
- 应用名和窗口标题；
- 外框、内容区、捕获帧和显示器几何；
- 当前几何/绑定 generation；
- 前台状态；
- 激活请求与实际观察结果；
- 进程或窗口重建后的刷新/重绑。

Windows adapter 尽量包装现有行为。macOS 可组合 `NSRunningApplication`、`SCWindow`、`CGWindowID`、PID 和 bundle identifier。

窗口发现不得只依赖标题，也不得在观察真实客户端前硬编码猜测 bundle identifier。支持多候选和用户手动选择；持久化稳定提示，不持久化旧 PID/window ID。

## 6. 权限与稳定应用身份

- Screen capture 使用支持的 preflight/request API；Accessibility 使用支持的 trust/prompt API。
- 缺失或撤销权限是明确、可操作状态，不是高速重试条件。
- 不修改 TCC，不请求 root 绕过。
- Terminal/Python 权限只算开发证据。
- `DesktopWindowTarget` 和权限边界建立后，应尽早构建具有稳定 bundle identifier 的内部 `.app`，验证 `/Applications` 启动、重启/重新打包后的权限持久化以及撤销权限后的错误状态。
- 不从 DMG 内直接运行作为标准验收路径。
- `codesign --sign -` 或其他 ad-hoc 签名不能作为公开发布证据。

## 7. ScreenCaptureKit 生产截图

连续自动化必须使用持久 `SCStream`：

```text
SCShareableContent（发现/重绑时）
  → selected SCWindow
  → SCContentFilter(desktopIndependentWindow:)
  → SCStreamConfiguration
  → persistent SCStream
  → CMSampleBuffer callback
  → bounded latest-frame publication
```

强制要求：

- 不得每帧重新调用 `SCShareableContent`；
- 不得每帧创建 filter/config；
- 不得使用每帧 `SCScreenshotManager`；
- `showsCursor = false`；
- callback 不运行 OCR、模板、YOLO、task 或 Qt 更新；
- 只发布最新完整帧，存储有界，慢消费者不能造成队列增长；
- 发布给 consumer 的内存必须拥有或稳定，不得被底层异步覆盖；
- 输出统一为 BGR `numpy.ndarray`、`uint8`、`(height, width, 3)`；
- 生产帧只含游戏内容区，不含光标、标题栏、阴影、边框或其他桌面。

一次性截图只允许显式“截图测试”和低频诊断，不能成为 task executor 的 fallback。

## 8. 几何与坐标

必须区分：

1. macOS 全局逻辑点；
2. `SCWindow.frame` 外框；
3. ScreenCaptureKit 实际帧像素；
4. 游戏内容区；
5. Qt logical coordinate；
6. display/Retina scale；
7. 游戏内部渲染分辨率。

不得直接把 `SCWindow.frame.width/height` 当作内容像素尺寸或任务分辨率。

- 视觉管线以实际捕获帧尺寸为事实来源；
- 若系统帧含装饰区域，必须通过可测试的规则裁出客户区；
- task/识别统一使用帧内物理像素；
- 平台后端执行“帧像素 → 全局逻辑点/CGEvent 坐标”转换；
- 每次输入绑定当前不可变 geometry snapshot/generation；
- 移动、resize、显示器切换、scale 变化或重绑开始时立即废弃旧帧/旧几何；
- 不得假设 scale 固定为 2.0。

调试信息必须能同时显示：`SCWindow` 外框、实际帧尺寸、内容区、display scale、输入帧坐标、最终 CGEvent 全局坐标和 generation。

## 9. Quartz 前台输入

生产输入使用公开 Quartz/Core Graphics CGEvent。

基础能力优先级：

1. key tap；
2.独立 key down/up 和 W/A/S/D 长按；
3. E/Q/R/F/Space/Shift/Tab 及 consumer 实际键集；
4. 左/右/中键 down/up/click；
5. 鼠标按钮保持；
6. 绝对坐标；
7. scroll；
8. 现有 consumer 键鼠组合；
9. 最后才是自由 relative X/Y。

任务可以在开始时请求激活目标，并等待观察到 frontmost。输入后端不得在每次事件前无条件重新激活应用或反复抢焦点。

每个普通事件或短原子批次前：

```text
验证 target 存在/PID 存活
→ 验证 target app 是系统 frontmost
→ 验证 input gate 与 geometry generation 有效
→ 才发送事件
```

原子批次不得跨越 sleep、frame wait、激活、权限提示或其他可能改变焦点的操作。

不得暗中回退到 `CGEvent.postToPid` 或把输入发给当前任意前台应用。

## 10. `ForegroundGuard`、`HeldInputState` 与 `release_all()`

必须在线程安全的统一边界中跟踪：

- synthetic held keys；
- synthetic held mouse buttons；
- 当前 owner/batch；
- focus-lost/shutdown/target-lost 状态；
- 当前 geometry generation。

失焦或失效时顺序：

1. 拒绝待发送普通事件；
2. 关闭新普通输入闸门；
3. 仅为已记录 held state 发布对应 key-up/button-up；
4. 即使某个 release 失败仍继续其余 release；
5. 清空内部状态；
6. 向 executor/consumer 报告明确 pause/stop reason；
7. 仅用户显式操作可恢复，不得自动循环抢焦点。

`release_all()` 必须幂等、可重复、目标消失后安全，并在事件发布失败时仍清空内部状态。

必须在焦点丢失、任务取消、executor stop、设备切换、游戏退出、fatal capture、权限撤销和应用退出时调用。

关闭顺序：阻断新输入 → `release_all()` → 停止 stream/workers → 销毁 Qt/Python 对象。

## 11. relative mouse 的分级语义

`relative_mouse` 不是整个 Mac 前台 MVP 的统一发布阻断项。

- basic menu/claim/backpack/enhancement 等不要求它；
- 持续 W/A/S/D、中键锁敌/居中、左右键保持和键鼠组合通过后，可据实开放对应 locked-gameplay consumer；
- 只有任意镜头 X/Y、精确路线转向和完整 camera parity 需要它。

relative mouse 未硬件通过时：

- 允许发布已通过的 basic MVP；
- 允许发布已通过的 locked-gameplay task；
- 必须拒绝声明 free-camera route、完整跑图、完整战斗或 Windows 功能对等；
- 任何明确要求 `relative_mouse=True` 的任务必须在执行前被 capability gate 阻止。

## 12. 键码

- task 使用稳定逻辑键名，如 `w a s d e q r f space shift tab 1 2 3`；
- macOS backend 统一转换为 `CGKeyCode`；
- task 和共享 common key map 不出现 Mac keycode；
- 公共 key map 不顶层导入 `win32con`；
- 不把 Windows VK 直接当作 Mac keycode；
- 为 OK-WW 实际使用键集建立完整测试。

## 13. Windows 回归

必须保持：

- WGC / BitBlt 选择与行为；
- 当前 Windows interaction；
- HWND 发现和选择；
- public capture/interaction/task API 与配置键；
- ADB/browser 现有行为。

优先使用窄 adapter 和 lazy import，不为目录对称重写稳定 Windows 实现。

## 14. 测试与 CI

自动化测试至少覆盖：

- Darwin 不加载 `win32*`，Windows 不要求 PyObjC；
- `DeviceCapabilities` 默认失败关闭、missing/supports 和 task preflight；
- target 生命周期、前台观察、激活确认和 rebind；
- BGRA→BGR、row stride、padding、ownership、latest-frame overwrite 和 bounded storage；
- scale 1.0/2.0/非整数假设、窗口偏移、标题栏裁剪和 generation replacement；
- key/button down/up、重复 down、单点 release 失败、幂等 release；
- focus loss、目标退出、permission loss、fatal capture 和 shutdown 顺序；
- `relative_mouse=False` 不阻断不要求该能力的任务；
- consumer task 声明覆盖和不兼容时执行前拒绝；
- Windows 回归。

CI 不安装游戏。真实窗口、TCC、输入效果和 task end-to-end 单独记录。

## 15. 性能与诊断

1920×1080 初始目标配置 30 FPS。低于稳定 20 FPS 时必须分析。

至少记录：

- 实际 capture FPS；
- latest frame age；
- overwrite/drop count；
- 当前 PID/window ID/geometry generation；
- stream rebuild/rebind count；
- permission/focus/input gate 状态。

不得为了提高通过率删除安全检查或改为无界队列。

## 16. 同一长期分支中的执行顺序

```text
A. 审计和中文约束修订
B. 平台安全 build/import 与 capability gate
C. DesktopWindowTarget、窗口发现、前台观察、权限和早期内部 app identity
D. 持久 SCStream、内容区与几何代次
E. Quartz 基础输入、ForegroundGuard、HeldInputState、release_all
F. consumer 真机基础/组合输入；之后再测 relative mouse
G. consumer task capability matrix 与端到端
H. Windows/macOS CI、稳定内部 .app、TCC、最终验收和 PR 准备
```

这些是同一开发分支内的阶段，不是 PR 拆分要求。

## 17. MaaEnd / MaaFramework 参考边界

可以参考其公开实现证明：窗口枚举、ScreenCaptureKit 截图、普通 Quartz 键盘、左/右/中键和固定坐标点击具有现实可行性。

不得照搬：

- 每次截图重新枚举并调用一次性 API；
- 直接用 `SCWindow.frame` 作为内容像素尺寸；
- 每次输入前自动激活目标；
- ad-hoc/不稳定应用身份作为权限验收；
- 后台 controller 作为本分支增加后台支持的理由。

本 MVP 不引入 MaaFramework binary/dylib。未来引入需要独立 ADR。

## 18. 证据和声明

provider capability 仅使用：

1. `not-implemented`；
2. `unit-tested`；
3. `hardware-validated`；
4. `packaged-app-validated`。

consumer task 另用 `validated`、`experimental`、`unsupported`。

文档、UI、README、PR 和 release note 必须采用较低的真实证据。每条硬件证据记录 commit SHA、Mac/系统/游戏版本、分辨率、窗口模式、display scale、步骤和结果。回归重新打开对应 gate。

公开分发还要求 Developer ID Application、Hardened Runtime、timestamp、notarization、staple 和干净用户环境验证。
