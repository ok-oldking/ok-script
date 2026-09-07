# ADR 0001：原生 Mac 比例适配的框架边界

状态：accepted（2026-09-05，用户批准 contributor 本地集成分支实施；upstream 审查仍待最终 MVP）

权威配套决策：OK-WW `docs/development/decisions/0001-native-macos-aspect-ratio.md`。

允许 consumer 显式接受 Mac 原生16:10内容帧，不要求强制1920×1080。框架保留原生BGR帧和物理像素坐标契约，不拉伸/伪裁切整帧。通用参考坐标与锚点换算可在框架复用；游戏页面布局策略只在consumer选择。既有Windows16:9和默认公开API行为不变。

替代方案、理由：AXSize真机不可写，强制窗口/系统分辨率不可行；虚拟显示仍禁止；整帧拉伸或中央裁切破坏识别与坐标，不采用。未知比例和未验证任务不自动开放。

不增加权限或依赖，不变更ScreenCaptureKit/Quartz前台架构。foreground、release_all、权限、生命周期、当前geometry generation和旧帧拒绝全部保留。安全影响仅为新增布局换算错误风险，需显式锚点、边界与回归测试控制。

测试包括16:9原结果、16:10锚点/缩放/非整数尺寸、识别返回真实帧坐标、未知比例拒绝、resize安全契约以及完整无游戏测试。游戏识别/点击/任务端到端和packaged app仍单独验收，不以单元测试声明支持。

开发继续独立仓库与sibling editable，最终消费不可变版本。无持久配置格式破坏。回滚先停止consumer任务并撤销16:10接入，再撤销新增框架行为，保留此前安全修复。无第三方代码、额外许可证、个人截图或凭证引入。仅本地提交，不推送或开PR。
