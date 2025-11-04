# ok-script 进阶使用指南

本文档是 [ok-script 自动化脚本开发指南](../quick_start/README.md) 的进阶补充，旨在帮助开发者更深入地利用框架的高级功能，并结合
CI/CD 流程实现项目的自动化管理。

## 目录

- [1. 模板匹配 (Template Matching)](#1-模板匹配-template-matching)
- [2. 多语言国际化 (i18n)](#2-多语言国际化-i18n)
- [3. 自动化测试](#3-自动化测试)
- [4. 使用 GitHub Action 自动化打包与发布](#4-使用-github-action-自动化打包与发布)
    - [关键步骤解析](#关键步骤解析)
    - [Sync Repositories 的国内镜像功能](#sync-repositories-的国内镜像功能)
    - [配置多地区更新源](#配置多地区更新源)
    - [打包产物说明](#打包产物说明)
    - [加速构建速度](#加速构建速度)

## 1. 模板匹配 (Template Matching)

`ok-script` 的模板匹配工作流基于 COCO 数据集格式，这使得标注和管理特征点（模板图片）变得高效且精准。

### 核心优势

* **保留相对位置**: COCO 格式可以记录每个标注模板在原始截图中的**相对位置**。`ok-script`
  利用这一信息，在匹配时可以智能地缩小搜索区域，从而极大地提升匹配速度和准确度。
* **高分辨率优先**: 建议标注时使用的截图采用您计划支持的**最高分辨率**（例如
  4K）。当最终用户在较低分辨率下运行时，框架会自动将高清的模板素材缩放以进行匹配，保证了向下的兼容性和识别效果。

### 操作流程

1. **标注工具**: 使用任何支持导出 COCO 格式的标注工具。推荐使用 **`label-studio==1.15.0`**，因为新版本导出的 COCO
   格式存在兼容性问题。
2. **放置素材**: 将标注工具导出的 `result.json` 文件以及对应的图片文件夹（通常是 `upload` 文件夹）完整地放入项目的
   `assets` 目录下。
3. **自动处理**: 运行 `python main_debug.py` 启动程序。在 Debug 模式下，`ok-script` 会自动检测 `assets` 目录下的 COCO
   文件，并执行**切图和压缩**操作，将大图中的各个标注区域切割成独立的模板图片，并进行优化，以备后续 `find_feature` 等方法调用。

## 2. 多语言国际化 (i18n)

为脚本添加多语言支持可以扩大用户群体，`ok-script` 内置了简便的国际化流程。

### 实现步骤

1. **创建语言文件**:
   在项目根目录下，创建语言文件。目录结构必须遵循 `i18n/<语言代码>/LC_MESSAGES/` 的格式，例如：
    * 英文: `i18n/en_US/LC_MESSAGES/ok.po`
    * 简体中文: `i18n/zh_CN/LC_MESSAGES/ok.po`
2. **编辑 `.po` 文件**: 在这些文件中，按照 `gettext` 格式编辑您的翻译字符串。
3. **一键编译**: 修改 `.po` 文件后，无需执行任何命令行操作。只需在 `ok-script` 客户端的**开发者工具**中，点击**“编译
   i18n”**按钮。框架会自动将所有 `.po` 文件编译成二进制的 `.mo` 文件，程序运行时将自动加载对应的语言。

## 3. 自动化测试

为 Task 编写单元测试是保证脚本健壮性的关键。`ok-script` 提供了 `TaskTestCase` 基类，使得测试变得非常简单。

### 测试实践

* **稳定环境**: 测试的核心是使用 `self.set_image()` 将屏幕输入固定为一张静态图片，从而创造一个稳定、可复现的运行环境。
* **用户问题复现**: 除了使用自己截取的标准测试图，您还可以将**用户打包上传的截图文件**
  作为测试图片。这是一种非常高效的调试手段，可以帮助您快速定位并解决在特定用户环境中出现的问题。

**示例：使用用户截图定位问题**

```python
# file: tests/test_user_issue.py
from ok.test.TaskTestCase import TaskTestCase
from src.tasks.MyProblematicTask import MyProblematicTask


class TestUserIssue(TaskTestCase):
    task_class = MyProblematicTask

    def test_scenario_from_user_screenshot(self):
        # 1. 使用用户提供的截图文件
        self.set_image('tests/user_screenshots/user_bug_report_01.png')

        # 2. 调用在用户环境中出错的特定方法
        result = self.task.some_method_that_failed()

        # 3. 断言修复后的行为是否符合预期
        self.assertIsNotNone(result, "The method should now handle this scenario correctly.")
```

### 运行测试

#### 运行所有测试

要一次性执行 `tests/` 目录下的所有测试用例，可以直接运行项目根目录下的 `run_tests.ps1` 脚本。

#### 在 PyCharm 中运行单个测试

为了进行更精细的调试，例如只运行一个测试文件或文件中的某个特定方法，可以直接在 PyCharm 中操作：

1. 在代码编辑器中，右键点击测试文件或某个 `test_...` 方法。
2. 选择 "Run 'Unittests in ...'"。

**重要提示**：首次在 PyCharm 中运行测试时，需要修改其“运行/调试配置”(Run/Debug Configuration)。请确保**“工作目录”(Working
directory)** 设置为项目的**根目录**。否则，测试脚本会因为找不到 `tests/images/` 等相对路径下的文件而执行失败。

## 4. 使用 GitHub Action 自动化打包与发布

您提供的 `.github/workflows/build.yml` 文件定义了一个完整的自动化流程（CI/CD），它会在您每次推送新的版本标签（如 `v1.0.0`
）时，自动完成测试、打包和发布。

该流程的核心是 **PyAppify** ([https://github.com/ok-oldking/pyappify](https://github.com/ok-oldking/pyappify))，这是一个专门用于将
Python 项目打包成独立 Windows 可执行文件的工具，它通过项目根目录下的 `pyappify.yml` 配置文件进行驱动。

### 关键步骤解析

1. **触发条件 (`on`)**: 工作流由推送 `v*` 格式的 Git 标签触发，是标准的版本发布方式。
2. **安装依赖与环境设置 (`Install dependencies`)**: 读取 `requirements.txt` 并安装所有依赖，为后续步骤做准备。
3. **源码内联 (`inline_ok_requirements`)**: 将 `ok-script` 框架源码直接集成到项目中，使得最终打包的 `.exe` 完全自包含，简化用户安装。
4. **运行自动化测试 (`Run tests`)**: 执行 `tests/` 目录下的所有单元测试，作为发布的“质量门禁”。任何测试失败都会中断流程。
5. **同步仓库与生成更新日志 (`Sync Repositories`)**: 一个自定义 Action，用于将部分代码同步到轻量级的更新库，并自动生成两个版本标签之间的更新日志。
6. **打包可执行文件 (`Build with PyAppify Action`)**: 调用 PyAppify 工具将 Python 项目打包成独立的 Windows 可执行文件。
7. **创建 GitHub Release (`Release`)**: 在 GitHub 上创建新的 Release，使用自动生成的更新日志作为描述，并将打包好的可执行文件作为附件上传。

### Sync Repositories 的国内镜像功能

`Sync Repositories` 步骤的一个主要用途是**同步代码到国内镜像仓库**。对于无法流畅访问 GitHub 的国内用户，他们可以通过配置好的国内
Git URL 进行脚本的自动更新，保证了更新渠道的畅通。

### 配置多地区更新源

为了让不同地区的用户使用不同的更新源，您需要在 `pyappify.yml` 文件中定义多个 `profiles`。这允许您为同一个项目打包出多个版本，每个版本内嵌了不同的更新地址。

**`pyappify.yml` 配置示例:**

```yaml
name: "ok-ww"
uac: true

profiles:
  # 面向国内用户的配置
  - name: "China"
    git_url: "https://cnb.cool/ok-oldking/ok-wuthering-waves.git"
    # ... 其他配置
  # 面向全球用户的配置
  - name: "Global"
    git_url: "https://github.com/ok-oldking/ok-ww-update.git"
    # ... 其他配置
```

### 打包产物说明

`PyAppify Action` 成功运行后，通常会生成以下文件：

* `ok-ww-win32-China-setup.exe`: 面向国内用户的完整安装包。
* `ok-ww-win32-Global-setup.exe`: 面向全球用户的完整安装包。
* `ok-ww-win32-online-setup.exe`: 在线安装包，需要联网下载资源，不推荐普通用户使用。
* `ok-ww-win32.zip`: **构建加速文件**。它包含了本次构建的启动器 `.exe`，**无法直接运行**，其主要目的是用于加速下一次的构建流程。

### 加速构建速度

启动器 `.exe` 文件（即 `ok-ww-win32.zip` 内的文件）通常只在项目图标变更或启动器版本升级时才需要重新打包。在日常仅更新
`Task` 脚本代码的情况下，我们可以复用上一次发布中的启动器来大幅缩短 GitHub Action 的构建时间。

为此，可以在 `pyappify-action` 步骤中增加 `use_release` 配置：

```yaml
- name: Build with PyAppify Action
  id: build-app
  uses: ok-oldking/pyappify-action@master
  with:
    # 使用上一个稳定版本的 Release 来获取已打包的启动器，从而跳过耗时的打包过程
    use_release: https://api.github.com/repos/ok-oldking/ok-wuthering-waves/releases/tags/v2.7.12
```

**注意**: 您需要将上面的 URL 替换为您自己项目的上一个稳定 Release 的 API 地址。这样配置后，Action 会直接下载并使用该版本中的
`ok-ww-win32.zip`，从而跳过编译启动器exe的步骤。