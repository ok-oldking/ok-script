# 快速开始

本指南将帮助您快速开始使用 ok-script模板项目 `ok-script-boilerplate` 创建自己的项目。

## 1. Fork 项目

访问模板项目主页 [https://github.com/ok-oldking/ok-script-boilerplate](https://github.com/ok-oldking/ok-script-boilerplate)
并点击页面右上角的 "Fork" 按钮，将项目复刻到您自己的 GitHub 仓库中。

## 2. Clone 项目

将您复刻的项目克隆到本地。建议为您自己的项目起一个新名字。

```bash
git clone https://github.com/YOUR_USERNAME/your-project-name.git
cd your-project-name
```

*请将 `YOUR_USERNAME` 和 `your-project-name` 替换为您的 GitHub 用户名和您项目的名称。*

## 3. 安装 Python 3.12

请确保您的系统已经安装了 **Python 3.12**
版本。此项目仅支持该版本。您可以从 [Python 官方网站](https://www.python.org/downloads/) 下载并安装。

## 4. 创建虚拟环境 (可选)

为了保持项目依赖的隔离，建议您在 Windows 环境下创建一个虚拟环境。

```bash
python -m venv venv
venv\Scripts\activate
```

## 5. 安装依赖

使用 pip 安装项目所需的所有依赖包。

```bash
pip install -r requirements.txt
```

## 6. 修改 `config.py`

此文件是项目的核心配置文件。您**必须**根据您要适配的游戏类型，正确配置 `windows` 或 `adb` 部分，**至少需要配置其中一项**。

打开 `src/config.py` 文件，找到并修改以下配置：

* **`windows`**: 如果您适配的是 **Windows 客户端游戏**，请填写此部分。
    * `exe`: 游戏的可执行文件名列表，例如 `['StarRail.exe']`。
    * `interaction`: 交互方式，根据游戏类型选择，例如 `Genshin`, `PostMessage`, `Pynput` 等。
* **`adb`**: 如果您适配的是 **安卓模拟器或真机游戏**，请填写此部分。
    * `packages`: 游戏的包名列表，例如 `['com.abc.efg1']`。

*您可以同时保留 `windows` 和 `adb` 的配置，脚本会根据实际运行的游戏窗口或设备进行匹配。*

## 7. 运行脚本

项目提供了两种运行模式：

* **调试模式**:
  ```bash
  python main_debug.py
  ```
  此模式会产生额外的日志，并在游戏界面上绘制方框来标注正在寻找的目标和区域，方便开发和调试。

* **正式模式**:
  ```bash
  python main.py
  ```
  此模式为正式运行版本，不会在游戏界面上绘制额外内容。

> **重要提示**:
> - 如果您适配的是 **Windows 游戏**，为了程序能正常交互，需要以 **管理员权限** 运行脚本。
> - 如果您使用 PyCharm 或 VSCode 等 IDE，请 **右键点击 IDE 图标，选择“以管理员身份运行”**，然后再从 IDE 中启动脚本。
> - 如果您适配的是 **模拟器游戏**，则 **不需要** 管理员权限。

## 8. 测试截图功能

在程序界面中，点击 "截图测试" 按钮。程序会截取当前屏幕并保存。请检查项目 `screenshots` 目录下是否生成了新的截图文件，以确认功能正常。

## 9. 运行诊断任务

点击界面上的 "运行诊断任务" 按钮。这将执行一个预设的诊断任务，帮助您检查环境和配置是否正确。

## 10. 自定义你的任务

项目的核心在于任务的扩展。您可以根据您的具体需求，修改示例任务文件或创建新的任务文件：

* **`src/tasks/MyOneTimeTask.py`**: 用于实现只需要执行一次的单次任务（例如，点击签到）。
* **`src/tasks/MyTriggerTask.py`**: 用于实现基于特定触发器（如时间、图像识别）循环执行的任务（例如，自动战斗）。

通过模仿这两个文件的结构，您可以创建更多符合您业务逻辑的 Task。
