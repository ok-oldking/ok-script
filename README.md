# ok-script

## 无界面、桌面与 Web 模式

自动化核心现已与 Qt 解耦。使用 `ok-script` 可无界面运行，使用
`ok-script[qt]` 启用原有桌面界面，或使用 `ok-script[web]` 启用 FastAPI
浏览器界面；对应命令为 `ok run_task`、`ok gui` 和 `ok web`。详见
[运行时架构](docs/architecture.md)。

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

只安装应用所需的依赖配置。`default` 为无界面模式，Web、Qt、ADB 和 OCR
能力分别按需安装：

```powershell
python -m pip install "ok-script[default]"
python -m pip install "ok-script[qt]"
python -m pip install "ok-script[web]"
python -m pip install "ok-script[adb]"
python -m pip install "ok-script[ocr]"
```

ok-script 不会自动选择 OpenCV。用户必须根据自己的应用选择版本，并且只安装
一个变体：`opencv-python`、`opencv-contrib-python`、`opencv-python-headless`
或 `opencv-contrib-python-headless`。

以无界面模式开发本仓库时，同时安装 `pyproject.toml` 中的 `default` 和 `dev`
依赖组；再根据需要添加 `--group web`、`--group qt`、`--group adb` 或
`--group ocr`：

```powershell
python -m pip install --editable . --group default --group dev
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

## 致谢

ok-script 的开发离不开以下开源项目：

- [PyAppify](https://github.com/ok-oldking/pyappify)：用于应用更新和打包。
- [OnnxOCR](https://github.com/ok-oldking/OnnxOCR)：提供支持 Intel NPU 的 OCR，
  支持通过 OpenVINO 或 ONNX Runtime 推理，并使用 PaddleOCR v5 模型。
- [PySide6](https://wiki.qt.io/Qt_for_Python)：提供基于 Qt 的桌面界面绑定。
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)：Qt
  界面使用的 Fluent UI 组件。
- [OpenCV](https://opencv.org/)、[NumPy](https://numpy.org/) 和
  [Pillow](https://python-pillow.org/)：用于图像处理和计算机视觉。
- [FastAPI](https://fastapi.tiangolo.com/)、[Uvicorn](https://www.uvicorn.org/)
  和 [pywebview](https://pywebview.flowrl.com/)：用于 Web 界面支持。
- [adbutils](https://github.com/openatx/adbutils)：用于 Android 设备连接。

上述依赖均受其各自许可证约束，详情请参阅对应项目页面。

## 许可证

本项目采用 [Apache License 2.0 + Commons Clause 及附加条款](LICENSE.txt)。

允许的使用方式：

- 可用于闭源项目或商业项目。
- 可以 fork、本项目改进，并保持 fork 开源且免费。

限制：

- 禁止直接出售本项目，或仅改名、稍作修改后将其作为竞争产品出售或推广。
- 禁止将本项目用于黑客攻击、未授权访问、恶意软件、欺诈或其他违法活动。
- 任何使用 ok-script 的项目，都必须在项目网站、GitHub 或软件本身至少一处提及并链接 [ok-script.com](https://ok-script.com/) 或 [ok-script GitHub](https://github.com/ok-oldking/ok-script)。
- Qt UI 的使用还必须遵守 [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 的许可证。
