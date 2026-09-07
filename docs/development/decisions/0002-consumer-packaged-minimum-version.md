# ADR 0002：consumer 打包最低版本与框架设计基线分离

日期：2026-09-06。状态：`accepted`（用户授权 contributor 集成分支；upstream 尚未接受）。

权威产品决策位于配套 OK-WW `docs/development/decisions/0003-macos-packaged-minimum-version.md`：现有包的 Python/PySide6 wrapper 为 macOS 15.0，当前 OK-WW packaged MVP 因此收窄为 Apple Silicon、macOS 15+。其 285 个 native 文件审计与关键库直接复核、替代方案、用户安装影响、恢复 13/14 条件和产品回滚边界由该 ADR 记录。

框架公开 API 设计与通用 host gate 继续保持 macOS 13+，不提高最低版本判断，不删除 13.x API 兼容路径或契约测试。consumer 二进制基线不意味着框架 API 需要 15+；API 设计目标也不能证明完整依赖组合已在 13/14 运行。各 consumer 对自己的完整包与目标系统负责。

替代方案中，统一提高框架 gate 会无证据限制其他 consumer，因此不采用；降低 plist/Mach-O 标记不能补齐运行时兼容性，因此禁止；替换或重建整套 Python/Qt 依赖及恢复旧系统支持留给独立 ADR 与完整验证。此次无框架运行时、公共 API、依赖或配置迁移。

ScreenCaptureKit、Quartz 等公开 API、foreground guard、held state/release_all、新鲜帧/geometry 与失败关闭不变；无后台、私有 API、虚拟显示、注入、root 或 TCC 操作。bundle ID、签名、权限策略不变。Windows、ADB/browser、任务契约和依赖不受本决定影响；实际 Windows CI 必须按提交 SHA 另验，不以影响分析或旧包证据替代。

验收保持 source/unit、source/hardware、packaged/hardware 分开。框架 host gate 的 13+ 契约继续测试；OK-WW 负责 15.0 metadata/plist/all-native minos 检查，以及新包的真机/TCC/任务验收。当前更改不新增签名、公证或实机证据，最终 PR 和公开发行门槛不变。

开发仍使用 sibling editable，最终 consumer 使用维护者接受的不可变框架版本或 SHA。本次无新增第三方代码或许可证义务。回滚由 consumer 先停止任务、保留精确产物与数据并撤回不成立的发行声明；不能仅回滚文字就恢复 13/14 支持，框架 13+ gate 和已有安全修复不需撤销。
