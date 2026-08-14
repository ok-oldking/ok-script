# ok-script

[简体中文](README.md) | [English](README_en.md)

[![Discord](https://img.shields.io/discord/296598043787132928?color=5865f2&label=%20Discord)](https://discord.gg/vVyCatEBgA)

基于计算机视觉的 Python 自动化框架，面向 Windows 应用、Windows 游戏、安卓模拟器和 ADB 设备。

ok-script 提供 UI、截图与输入、设备控制、OCR、模板匹配、调试浮层、自动化测试、打包和增量更新能力。它使用 COCO 格式管理模板素材，并支持分辨率自适应与多语言界面。

## 特性

- 纯 Python 实现，免费开源，可直接使用 pip 生态中的第三方库
- 同一套任务代码可支持 Windows 客户端、安卓模拟器和 ADB 设备
- 支持 OCR、OpenCV 模板匹配以及 YOLO 等视觉方案
- 基于 COCO 标注管理模板素材，并根据屏幕分辨率自动缩放
- 内置截图、输入、设备控制和可视化调试工具
- 支持自动化测试、GitHub Actions 构建和安装包发布
- 支持多语言国际化和在线增量更新

## 快速安装

ok-script 支持 Python 3.11 及以上版本，推荐使用 Python 3.12。

```powershell
python -m pip install ok-script
```

如果要创建完整的自动化项目，建议从 [`ok-script-app`](https://github.com/ok-oldking/ok-script-app) 模板开始，而不是直接在本仓库中编写业务脚本。

## 文档

从[文档中心](docs/index.md)选择适合你的阅读路径：

1. [游戏自动化入门](docs/intro_to_automation/README.md)：了解截图、识别、决策和输入的基本原理
2. [快速开始](docs/quick_start/README.md)：从模板仓库创建并运行第一个项目
3. [进阶指南](docs/after_quick_start/README.md)：模板匹配、国际化、测试和发布
4. [API 参考](docs/api_doc/README.md)：`Box`、`BaseTask` 及常用任务 API

想先体验完整工具链，也可以使用基于 ok-script 的按键精灵项目 [`ok-py`](https://github.com/ok-oldking/ok-py)。

## 界面预览

| 任务配置 | 截图与交互 |
| --- | --- |
| ![任务配置界面](docs/ok_py/image_tasks.png) | ![截图与交互界面](docs/ok_py/image_capture.png) |

| 脚本与 API | 模板管理 |
| --- | --- |
| ![脚本与 API 界面](docs/ok_py/image_scripting.png) | ![模板管理界面](docs/ok_py/image_template.png) |

[查看界面与开发工具完整说明](docs/interface.md)，包括模板识别调试浮层。

## 使用 ok-script 的项目

- [ok-script 应用模板](https://github.com/ok-oldking/ok-script-app)
- [鸣潮](https://github.com/ok-oldking/ok-wuthering-waves)
- [原神](https://github.com/ok-oldking/ok-genshin-impact)（停止维护，后台过剧情仍可用）
- [少女前线 2](https://github.com/ok-oldking/ok-gf2)
- [崩坏：星穹铁道](https://github.com/Shasnow/ok-starrailassistant)
- [星痕共鸣](https://github.com/Sanheiii/ok-star-resonance)
- [二重螺旋](https://github.com/BnanZ0/ok-duet-night-abyss)
- [卡厄思梦境](https://github.com/baoxin1100/ok-kes)
- [阴阳师](https://github.com/YunLiuZ/ok-Onmyoji)
- [白荆回廊](https://github.com/ok-oldking/ok-baijing)（停止维护）
- [明日方舟：终末地](https://github.com/AliceJump/ok-end-field)
- [异环](https://github.com/BnanZ0/ok-nte)

## 社区与发布

- 开发者 QQ 群：938132715
- [PyPI](https://pypi.org/project/ok-script/)
- [GitHub](https://github.com/ok-oldking/ok-script)

## 许可证

本项目采用 [AGPL-3.0 许可证](LICENSE.txt)。
