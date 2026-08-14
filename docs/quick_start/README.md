# 快速开始

[English](../en/quick_start.md) · [文档中心](../index.md) · [进阶指南](../after_quick_start/README.md) · [API 参考](../api_doc/README.md)

本指南帮助你使用 ok-script 模板项目 `ok-script-app` 创建并运行自己的自动化项目。完成后，你将能连接 Windows 游戏或安卓设备、运行诊断，并开始编写任务。

## 开始之前

- Windows 10 或 Windows 11
- Python 3.11 或更高版本（推荐 Python 3.12）
- Git
- Windows 客户端游戏，或已启用 ADB 的安卓模拟器/设备

## 1. Fork 项目

访问 [`ok-script-app`](https://github.com/ok-oldking/ok-script-app)，点击页面右上角的 **Use this template**，从模板创建自己的 GitHub 仓库。

## 2. Clone 项目

将您复刻的项目克隆到本地。建议为您自己的项目起一个新名字。

```bash
git clone https://github.com/YOUR_USERNAME/your-project-name.git
cd your-project-name
```

*请将 `YOUR_USERNAME` 和 `your-project-name` 替换为您的 GitHub 用户名和您项目的名称。*

## 3. 安装 Python

框架支持 Python 3.11 及以上版本，推荐使用 **Python 3.12**。可以从 [Python 官网](https://www.python.org/downloads/) 下载。安装后确认版本：

### Python 下载渠道

中国大陆用户推荐优先使用国内镜像站：

- **清华大学开源镜像站**：访问[清华大学 Python 镜像仓库](https://mirrors.tuna.tsinghua.edu.cn/python/)，选择所需版本并下载安装包。
- **华为云镜像站**：访问[华为云 Python 镜像](https://mirrors.huaweicloud.com/python/)，选择对应版本下载。
- **官方渠道**：网络顺畅时，可前往 [Python 官方网站 Downloads 页面](https://www.python.org/downloads/)下载。

在版本目录中，Windows 64 位系统通常应选择名称包含 `amd64.exe` 的安装程序。安装时建议勾选 **Add Python to PATH**。

```powershell
python --version
```

## 4. 创建虚拟环境

建议为项目创建独立的虚拟环境，避免依赖冲突。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止激活脚本，可以直接使用 `.\.venv\Scripts\python.exe` 执行后续命令。

## 5. 安装依赖

使用 pip 安装项目所需的所有依赖包。

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 6. 修改 `config.py`

此文件是项目的核心配置文件。您**必须**根据您要适配的游戏类型，正确配置 `windows` 或 `adb` 部分，**至少需要配置其中一项**。

打开 `src/config.py` 文件，找到并修改以下配置：

- **`windows`**：适配 Windows 客户端游戏时填写。
  - `exe`：游戏可执行文件名列表，例如 `['StarRail.exe']`。
  - `start_exe`：是否由脚本启动并检查游戏进程，默认为 `True`。设为 `False` 后，启动任务时不会自动启动或检查游戏。
  - `start_method`：启动游戏的方式，默认为 `start`，也可使用 `os.startfile`。
  - `interaction`：交互方式，例如 `Genshin`、`PostMessage` 或 `Pynput`。
- **`adb`**：适配安卓模拟器或真机时填写。
  - `packages`：游戏包名列表，例如 `['com.abc.efg1']`。

*您可以同时保留 `windows` 和 `adb` 的配置，脚本会根据实际运行的游戏窗口或设备进行匹配。*

## 7. 运行脚本

项目提供了两种运行模式：

- **调试模式**

  ```powershell
  python main_debug.py
  ```

  此模式会产生额外的日志，并在游戏界面上绘制方框来标注正在寻找的目标和区域，方便开发和调试。

- **正式模式**

  ```powershell
  python main.py
  ```

  此模式为正式运行版本，不会在游戏界面上绘制额外内容。

> **重要提示：** Windows 游戏的输入方式可能需要管理员权限。如果交互没有响应，请以管理员身份启动终端或 IDE。模拟器和 ADB 设备通常不需要管理员权限。

## 8. 测试截图功能

在程序界面中，点击 "截图测试" 按钮。程序会截取当前屏幕并保存。请检查项目 `screenshots` 目录下是否生成了新的截图文件，以确认功能正常。

## 9. 运行诊断任务

点击界面上的 "运行诊断任务" 按钮。这将执行一个预设的诊断任务，帮助您检查环境和配置是否正确。

## 10. 自定义你的任务

项目的核心在于任务的扩展。您可以根据您的具体需求，修改示例任务文件或创建新的任务文件：

- **`src/tasks/MyOneTimeTask.py`**：用于实现只需要执行一次的单次任务（例如，点击签到）。
- **`src/tasks/MyTriggerTask.py`**：用于实现基于特定触发器（如时间、图像识别）循环执行的任务（例如，自动战斗）。

通过模仿这两个文件的结构，您可以创建更多符合您业务逻辑的 Task。

## 下一步

- 阅读[进阶指南](../after_quick_start/README.md)，学习模板标注、测试、国际化和发布。
- 在 [API 参考](../api_doc/README.md)中查询截图、输入、OCR 和找图方法。
- 如果还不熟悉视觉自动化，先阅读[游戏自动化入门](../intro_to_automation/README.md)。
