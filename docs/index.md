# ok-script 文档中心

[English](en/index.md) · [项目主页](https://github.com/ok-oldking/ok-script)

文档按“理解原理 → 运行项目 → 深入开发 → 查询 API”的顺序组织。第一次使用时，建议依次阅读前两篇。

## 学习路径

| 文档 | 适合读者 | 主要内容 |
| --- | --- | --- |
| [游戏自动化入门](intro_to_automation/README.md) | 没有计算机视觉或自动化经验的读者 | 截图、图像分析、决策、输入和开发工具 |
| [快速开始](quick_start/README.md) | 准备创建第一个项目的开发者 | Fork 模板、配置环境、连接设备、运行和诊断 |
| [界面与开发工具](interface.md) | 想了解可视化工作流的开发者 | 任务配置、截图与交互、脚本、模板和调试浮层 |
| [进阶指南](after_quick_start/README.md) | 已经可以运行模板项目的开发者 | COCO 模板、i18n、自动化测试、打包和发布 |
| [API 参考](api_doc/README.md) | 正在实现任务逻辑的开发者 | `Box`、`BaseTask`、截图、输入、OCR 和找图 API |

## 最短上手路线

1. 安装 Python 3.12（框架最低支持 Python 3.11）。
2. 使用 [`ok-script-app`](https://github.com/ok-oldking/ok-script-app) 模板创建仓库。
3. 按照[快速开始](quick_start/README.md)配置 Windows 游戏或 ADB 设备。
4. 运行调试模式并完成截图测试。
5. 参考 [API 文档](api_doc/README.md)实现自己的任务。

## 常用链接

- [ok-script 源码](https://github.com/ok-oldking/ok-script)
- [ok-script 应用模板](https://github.com/ok-oldking/ok-script-app)
- [ok-py 可视化脚本工具](https://github.com/ok-oldking/ok-py)
- [PyPI 发布页](https://pypi.org/project/ok-script/)
- [文档网站构建说明](building-site.md)

发现文档与代码不一致时，请在 GitHub 提交 issue，并附上使用的 ok-script 版本、Python 版本和运行环境。
