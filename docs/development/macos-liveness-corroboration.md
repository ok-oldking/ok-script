# AppKit 否定的原绑定交叉核验（2026-09-06）

状态：源码及自动化通过；当前安装的内部包尚未包含本修复。

## 原因与最小变更

原 `_observe_process()` 在首次 AppKit 否定时立即清除当前窗口候选，辅助存活信号只在
后续判断永久退出时使用。因此 AppKit 不一致会中断战斗，即使原绑定窗口仍可验证。

现在仅在 `exists()` 检查仍有效的同一绑定时，允许同次同步交叉核验：

- AppKit 必须明确为 False；查询异常仍失败关闭。
- POSIX 与 CGWindow PID 存活证据必须都明确为 True；unknown 或单独 POSIX 不足以保活。
- 按原 PID/window ID 查询到的窗口 geometry 必须与绑定值完全一致。
- 同步前台 PID 必须匹配目标进程。

满足全部条件只确认目标仍存在，不直接授权事件、不改变 generation、不打开 guard。
实际普通输入仍逐次经过原 ForegroundGuard、新鲜帧、权限、geometry/generation 校验和
Quartz sink 的最终 pre-post check。没有宽限期、旧帧容忍、后台输入或自动 resume。

证据不完整时仍立即失效、release_all、暂停；之后即使证据恢复也必须显式启动。
移动/resize 有意不纳入免暂停范围。丢失绑定、首次绑定和重新枚举仍采用保守的原路径，
不会凭多个窗口中的一个猜测恢复。连续全阴性才升级 EXITED 的现有逻辑保持。

日志在 AppKit 否定交叉核验时记录各信号、geometry 一致性、前台是否匹配、target generation
与 decision，不记录窗口标题、账号、OCR 或个人路径；capture 证据继续由原诊断提供。

## 验证与交付边界

- 使用配套 OK-WW 的既有 Python 3.12 venv；未安装依赖、未引入 onnxruntime。
- 定向 transient-target：40 passed。
- 框架全量：647 passed、12 skipped、4 subtests passed。
- OK-WW `tests/test_macos*.py`：147 passed。
- 新增 13 项覆盖完整证据保留绑定、异常/unknown/窗口变动拒绝，以及 production interaction
  对旧帧、generation、失焦、窗口丢失、权限失效的拦截、held release 和不自动 rearm。
- 独立只读复核未发现绕过 guard/final pre-post 或自动恢复路径。
- Windows 真实回归：deferred / 未验证；Windows 实现文件未修改。
- source identity 新修复真机、packaged 新修复真机：未验证。未操作游戏、未热更新运行时脚本、
  未重建/替换安装 App，也未更改权限。

## 下一步与回滚

先构建新的内部包并核对 provenance、签名、依赖，再由用户确认可以退出当前任务后安装。
随后仅做一次 45–60 秒残像聚落战斗，观察交叉核验日志，不领取奖励或自动继续下一场。
若测试期间没有出现 AppKit 否定，仅能证明短时运行正常，不能称复现条件下修复已确认。

回滚只撤销本轮 `_observe_process` 原绑定交叉核验及其调用参数，保留既有多源退出确认、
capture freshness 和所有安全门；不得覆盖其他未提交工作。安装包仍保留原版本，不需回滚。
