# ok-script

类似于AirScript, 使用Python

## 优势

1. 开源免费, 依赖库均为开源方案, 支持pip install任何第三方库
2. 代码和打包流程完全由开发者控制, 不会上传服务器, 没有安全性隐患, 不容易被侦测和识别
3. 一套代码即可支持Windows安卓模拟器/ADB连接的虚拟机, Windows客户端游戏, 安卓系统直接运行(开发中)
4. 支持GUI以及Console运行, 也可以完全自己开发GUI
5. 支持Python3.7以上版本
6. 学习成本低, 自定义函数少, 也可以直接使用opencv, RapidOCR等api

## Example Usage

Basically you only need to write the Tasks and Scenes, the autoui framework will do all the heavy lifting.
[genshin/main.py](genshin/main.py)

```python
# Defining game scenes to handle different in-game situations through automated tasks
task_executor.scenes.extend([
    WorldScene(interaction, feature_set),
    StartScene(interaction, feature_set),
    MonthlyCardScene(interaction, feature_set),
    DialogCloseButtonScene(interaction, feature_set),
    DialogChoicesScene(interaction, feature_set),
    DialogPlayingScene(interaction, feature_set),
    BlackDialogScene(interaction, feature_set),
])

# Adding automated tasks for gameplay, such as dialog navigation and item collection
task_executor.tasks.extend([
    AutoPlayDialogTask(interaction, feature_set),  # speeding up the dialogs
    AutoChooseDialogTask(interaction, feature_set),  # choose dialog options
    AutoPickTask(interaction, feature_set),  # pickup items in world scene
    AutoLoginTask(interaction, feature_set),  # auto login and claim rewards
])
```

## Scenes

## Tasks

## Project Structure

- `autoui`: Framework code.
- `genshin`: Example Genshin Impact automation project
