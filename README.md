# ok-script
* ok-script 是基于图像识别技术, 纯Python实现的, 支持Windows窗口和模拟器的自动化测试框架。
* 框架包含UI, 截图, 输入, 设备控制, OCR, 模板匹配, 框框Debug浮层, 基于Github Action的测试, 打包, 升级/降级。
* 基于开发一个工业级的自动化软件仅需几百行代码。

## 优势

1. 纯Python实现, 免费开源, 依赖库均为开源方案
2. 支持pip install任何第三方库, 可以方便整合yolo等框架
3. 一套代码即可支持Windows安卓模拟器/ADB连接的虚拟机, Windows客户端游戏
4. 自适应分辨率
5. 使用coco管理图片匹配素材, 仅需一个分辨率下的截图就, 支持不同分辨率自适应
6. 可打包离线/在线安装setup.exe, 支持通过Pip/Git国内镜像在线增量更新. 在线安装包仅3M
7. 支持Github Action一键构建
8. 支持多语言国际化

### 使用

* 需要使用python 3.12
* 使用pip
```commandline
pip install ok-script
```
* 或者本地编译源码使用
```commandline
in_place_build.bat
```
* 链接目录到你项目的ok文件夹下
```commandline
mklink /d "C:\path\to\your-project\ok" "C:\path\to\ok-script\ok"
```

## 文档和示例代码

* [游戏自动化入门](docs/intro_to_automation/README.md)
* [快速开始](docs/quick_start/README.md)
* [进阶使用](docs/after_quick_start/README.md)
* [API文档](docs/api_doc/README.md)
* 开发者群: 938132715
* pip [https://pypi.org/project/ok-script](https://pypi.org/project/ok-script)


## 使用ok-script的项目：

* 鸣潮 [https://github.com/ok-oldking/ok-wuthering-wave](https://github.com/ok-oldking/ok-wuthering-waves)
* 原神(不在维护,
  但是后台过剧情可用) [https://github.com/ok-oldking/ok-genshin-impact](https://github.com/ok-oldking/ok-genshin-impact)
* 少前2 [https://github.com/ok-oldking/ok-gf2](https://github.com/ok-oldking/ok-gf2)
* 星铁 [https://github.com/Shasnow/ok-starrailassistant](https://github.com/Shasnow/ok-starrailassistant)
* 星痕共鸣 [https://github.com/Sanheiii/ok-star-resonance](https://github.com/Sanheiii/ok-star-resonance)
* 白荆回廊(停止更新) [https://github.com/ok-oldking/ok-baijing](https://github.com/ok-oldking/ok-baijing)