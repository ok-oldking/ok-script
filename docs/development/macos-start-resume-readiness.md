# macOS 显式启动／恢复的捕获就绪修复

## 当前统一契约（2026-09-06，源码收敛；尚无新包验收）

`DeviceManager.prepare_macos_capture(timeout=8, manual_window_id=None)` 是显式捕获准备的唯一入口，负责窗口选择/绑定、provider 准备和有界新鲜帧就绪。GUI“绑定并连接截图”、Start 与 Resume 均委派该入口；同一次 start 复用已准备好的 provider，不重复发现或二次准备。截图连接本身不等待用户切回游戏、不启动任务、不打开输入门。

Quartz `await_fresh_frame` 只重新验证当前捕获的帧与 geometry/generation，不执行 discovery 或 stream rebuild；`on_run()` 仍做原有前台、权限和最终安全检查。捕获恢复属于上述 DeviceManager 入口，不能由输入后端隐式修复。运行中的 2 秒新鲜帧门槛保持，过期帧拒绝输入并释放，显式恢复仍要求本次请求之后的新帧，不自动续跑。

下方各轮“最新源码”标题、测试数量及早期由 Quartz `on_run()` 恢复截图的描述保留为历史，当前实现以本节为准。新提交的自动化命令、结果与 exact SHA 另行记录；旧包、旧源码真机证据不升级为本修订的 packaged 验收，Windows 结果不能预填通过。

## 任务按钮可发起连接（最新源码，未打包）

Mac 一次性任务按钮不再因尚未创建 provider 导致 missing-capabilities 而禁用；
按钮代表连接/启动请求，不代表输入许可。明确 unsupported 仍禁用，Trigger 与其他
设备路径保持原门禁。StartController 先 prepare_macos_device、等待新鲜截图，再检查
所选任务能力，之后才进入前台交接与准备时间。执行前原有能力和安全门检查继续保留。
连接只接受现有唯一可信窗口/显式绑定，歧义、权限或 capture 失败均不入队、不运行任务。
手动连接和任务自动连接在成功后发送 adb_devices，任务卡立即更新，不再要求用户刷新。
自动化：框架 694 passed、12 skipped、4 subtests passed，覆盖连接成功通知、请求按钮、
连接/capture/能力失败不进入前台等待或执行。尚无该修订 packaged 真机证据。

## 截图连接与任务启动分离（最新源码，未打包）

Mac 截图页移除顶部执行器“开始”按钮，统一通过“绑定并连接截图”执行：
显式窗口选择 → bind → prepare provider → capture.wait_until_ready。
不调用 StartController、不等待前台、不倒计时、不启动任务或打开输入门。
8 秒仅为等待新鲜截图的失败上限，截图就绪立即返回，不是固定延迟。
连接失败显示错误，不提前报告截图已连接。任务页独立保留每任务准备时间。
定向测试 29 passed；本修订尚未进入安装包，真机截图连接待验。

## 每任务准备时间（最新源码，未打包）

用户确认默认 8 秒，不采用快捷键确认。Mac 一次性任务配置新增 `Preparation Seconds`，
独立按任务 Config 保存，范围整数 0–300 秒。切回游戏后才开始准备计时；期间每 100ms
只读观察前台，切走、取消、退出或更换绑定会取消本次启动。准备结束后才进入原启动流程。
不检测 Option，不识别“传送完成”；用户应根据任务自行设置足够的准备时间。
TriggerTask 保持实时触发语义；无指定任务的全局开始默认 8 秒。
准备期间不显示会遮挡/抢焦点的倒计时窗口，切走游戏即可取消；只记录准备秒数。
本次等待不启动新任务，不替代停止已有运行任务，准备场景前应先停止其他自动化。
此节取代下节“一置前即进入正常启动”的时序。尚无本修订 packaged 真机证据。

## 2026-09-06：用户前台交接取代主动激活（最新源码，尚未打包）

- Mac GUI 开始／恢复统一先只读等待已绑定 PID 进入前台，预算不超过 30 秒，
  用户可以取消等待；不检测 Option 或任何修饰键，也不调用 AppKit 激活。
- 进入正常启动阶段后结束取消等待界面，不反复显示对话框抢焦点。
  取消仅适用于前台交接；任务启动后的停止继续使用既有停止操作。
- PID 匹配只是交接条件，不是输入许可。后续正式绑定、capture readiness、
  新鲜帧、geometry/generation、ForegroundGuard 和最终 pre-post 检查全部保留。
  Quartz `on_run()` 发现游戏未在前台时明确失败，不主动抢回前台。
- 在交接完成后、修改任务前记录状态。启动失败只撤销本次新启用/入队任务，
  恢复原暂停及 exit-after 状态；不改 Trigger 持久偏好，不清除原有任务队列。
- 非 Windows 的 WindowsScheduleManager 明确 unsupported，不导入 COM、不执行
  schtasks、不启动同步线程、不删除缓存；Windows 原有 COM/CLI 路由保持。

自动化：指定游戏仓库虚拟环境，框架全量 663 passed、12 skipped、4 subtests passed；
游戏 Mac 相关 147 passed。涵盖前台交接、取消/超时/退出、失败回滚、暂停保持、
无主动激活和非 Windows 调度器隔离。平台测试替身不等于真实 Windows 或 packaged 证据。
本轮没有重建/替换已安装 App，没有运行新的游戏输入测试。
Windows deferred / 未验证；撤权用户取消；Developer ID/公证/Gatekeeper 未验证。
回滚仅撤销本轮 controller、等待界面、Quartz 激活策略和 scheduler 局部变更及对应测试，
不覆盖先前未提交工作、用户配置或现有内部包。

## 2026-09-06 补充：capture heartbeat 输入门槛

生产 ForegroundGuard 在 watchdog 与最终 pre-post 均检查当前 PublishedFrame 的
sequence、captured_monotonic、age、geometry 与 generation；无帧/无有效元数据、
非有限或负 age、超过 2 秒都报 MAC_CAPTURE_FRAME_STALE 并 release_all/pause。
SCStream running 本身不能放行，get_frame_packet 不返回过期帧。
新帧发布不自动重开门，显式 resume 必须取得请求之后的新帧；不比较图像内容。
新增 test_macos_frame_freshness 覆盖 held W/left 的停流 watchdog、生产 pause 回调、
停止后键鼠拒绝与新帧显式恢复。框架本轮全量 634 passed、12 skipped、4 subtests passed。
source/hardware 与 packaged/hardware 的本修复仍未验；Windows deferred / 未验证。
通用 open_path 另有 Mac/Windows 路由与路径参数测试，不更改 Windows 输入后端。

## 2026-09-06：修正单次 AppKit 否定误报退出（最新状态）

本节取代此前“一次进程 API False 即确认退出”的结论。单次 AppKit False/异常只进入
`MAC_TARGET_UNAVAILABLE`，清除公开可用 snapshot；首次失效立即返回安全门释放 held state，
不等待辅助枚举。后续至多每 0.5 秒观察一次 AppKit、POSIX `kill(pid, 0)` 与 CGWindow PID。
仅连续三次三项均明确否定才锁定 `MAC_TARGET_EXITED`；EPERM 视为存活，未知/矛盾不确认退出。
日志记录三项信号及计数，不记录窗口标题或个人画面。未采用可能陈旧的 SCK 帧作为存活证据。
显式恢复仍要求可信唯一窗口、新 target/capture generation、geometry 和新鲜帧，不自动续战。

自动化：框架全量 624 passed、12 skipped、4 subtests passed；游戏相关 132 passed、
3 subtests passed。新增覆盖 AppKit 瞬时否定、独立证据冲突、ESRCH/EPERM/未知错误、采样间隔、
正信号清零、首/末检查释放 held state 和旧 generation 拒绝。`git diff --check` 通过。
本修正尚未重新打包或安装；已安装旧包不含此修复。source identity 与 packaged identity 的
本轮战斗复测均未执行，历史真机证据不升级。Windows：deferred / 未验证。
权限撤销：用户取消／未执行；Developer ID、公证、Gatekeeper clean-user：未验证。
回滚仅移除此轮存活确认代码和对应测试，保留原有未提交修改；不得整仓 reset。


日期：2026-09-06。状态：自动化通过，修复版 packaged 真机待验。

## 根因与实现

暂停任务恢复、queued-start 及任务卡恢复可能直接调用 executor.start/on_run，
而 ScreenCaptureKit 正在 geometry rebuild，尚无有效 geometry。原安全门拒绝正确；
不能靠放宽 ForegroundGuard 修复。

在 ScreenCaptureKit 增加 `wait_until_ready()`，由 Quartz `on_run()` 的显式生命周期
统一调用，覆盖 start/resume/queued-start 和任务 enable。等待时不持有 input/guard lock，
原生截图失效及退出仍能立即关闭输入、释放 held state；成功后才运行原有 activation
观察与 guard.open 校验。安全门已打开时不重复等待或污染 input owner。

就绪要求：双权限有效、目标存在、running、有新 sequence 且时间不早于本次请求的帧、
geometry 与 target/capture generation 一致。轮询预算 8 秒、间隔 0.1 秒；窗口丢失时
至多每 0.5 秒重新发现，沿用稳定应用身份、尺寸过滤和歧义手选规则。原生枚举和
stream start/stop 自身的 lifecycle timeout 仍适用，单次原生调用可能跨过轮询截止；
截止后即使返回帧也不放行。permission/fatal/closed/exit 不进入无限恢复。

此处只恢复捕获；不自动激活、不在后台打开 guard。运行中失焦或窗口消失依旧暂停，
必须用户显式恢复。目标进程／窗口身份有歧义时不盲选、不挑第一个候选。
暂不承诺传送窗口丢失后无需人工恢复的完整无干预任务闭环。

TaskCard 的前台 provider 恢复改走既有 StartController 后台处理和错误提示，
不让 readiness 异常冒到 Qt 主线程。前台任务 unpause 仅在 start 成功后清暂停标志；
禁用任务的 stop/unpause 不再重开输入。非前台 provider 保持原有路径。

## 自动化证据

框架：使用配套游戏仓库 `.venv/bin/python -m pytest -o addopts='' -q`，
597 passed、12 skipped、4 subtests passed。
新增 `tests/test_macos_capture_readiness.py` 覆盖新鲜帧、geometry 重建、暂失恢复、
stale/generation/permission/fatal/closed/exit 拒绝、真实 executor 与 controller 的
resume/queued-start、TaskCard 路由、失败暂停保持，以及真实 target selection 排除
52×20 小浮窗，及重建等待期间 stop 不阻塞、不重开输入。
这些使用合成平台适配器，不是硬件/TCC/游戏验收。

配套游戏 Mac 相关与 NightmareNestTask：132 passed、3 subtests passed。
Windows 回归：deferred / 未验证；没有运行远端 Windows CI。

## 2026-09-06：区分瞬时窗口不可用与进程退出

用户报告战斗期间一次窗口查询缺失触发 MAC_TARGET_EXITED，但同 PID/window 后续
仍存在。本轮针对生命周期分类和恢复身份修改，不把该报告当成进程退出或战斗算法失败。

MacOSWindowTarget 在私有 `_last_bound_candidate` 中保留最近绑定身份，仅供恢复匹配；
公开 snapshot 仍立即清空 candidate、exists=False 并增加 generation，公开几何为空。
进程存活而窗口查询为空／查询抛错为 `MAC_TARGET_UNAVAILABLE`；进程存活 API 明确返回
不存在才锁定 `MAC_TARGET_EXITED`。查询异常不是进程退出证据。进程明确退出后该 target
不复活，也不接管其他同 bundle 进程，用户须重新绑定以创建新 target。

显式 refresh/readiness 只选择原 PID、bundle、application name 一致且满足尺寸/layer
约束的候选。窗口暂失后即使原 ID／标题重新出现，存在多个可信窗口仍要求人工选择；
不能用原位置、标题或第一个候选来猜游戏当前渲染面。此前已绑定且未丢失的窗口几何刷新
仍优先确切身份。恢复用的新候选提升 target generation，捕获重建后还要等待新的
capture generation、geometry、新 sequence 帧；旧帧和旧坐标不获准输入。

主页面 prepare_macos_device 只有无 target 时可首次绑定；既有失效 target 先调用
refresh_macos_window_target 关闭旧输入/捕获并尝试同进程恢复。失败或多候选时不隐式
bind 新对象；原进程结束需用户使用窗口绑定控件。单次 refresh 受枚举 timeout 约束，
窗口仍未返回时报告重试／人工选择，而不是自动替换目标。

ForegroundGuard 两次 target/foreground 检查均保留立即失败关闭；第二次检查中发生的
窗口丢失也归入目标不可用，不误归普通失焦。Quartz 仍立即释放 held state；没有新增
后台自动开门、无中断自动续战或失焦自动激活。readiness 遇到已退出进程或多候选立即
给出重新绑定／人工选择指引，不无限重试。

最终框架回归：613 passed、12 skipped、4 subtests passed；游戏 Mac 相关保持
132 passed、3 subtests passed。新增 16 项 transient target 测试覆盖主页面启动恢复、一次空查询、
同 ID 恢复、换 ID、查询异常、进程退出锁定、其他 PID/bundle/小浮窗拒绝、多主窗口
人工选择、两次 guard 检查的错误分类、held 清空和旧 generation 拒绝，以及真实
target/capture/Quartz 组合下显式恢复必须等待新帧。平台调用与 event sink 为合成适配器，
不冒充新包真机验证。Windows deferred / 未验证。

新包构建与真机结果见 consumer 内部包验收记录。回滚本轮应协调撤销私有恢复身份、
错误分类和同进程重绑限制的局部补丁，不丢弃先前工作树修改；旧包和用户数据保留。

## 通用边界与回滚

本轮不改 Windows provider、TCC、安全门条件、Quartz 最终 pre-post、依赖锁和公共发布身份。
source identity 旧真机与旧包真机证据不升级为本修复版证据。
权限撤销用户取消／未执行；Developer ID、公证、staple、Gatekeeper clean-user 未验证。
不能称内部包完整通过或上游 PR／公开发行就绪。

回滚仅撤销本轮 readiness、TaskCard 恢复和前台 unpause 的局部补丁，并协调回滚 consumer；
保留已有未提交实现及用户数据，不使用 reset/checkout/clean。
