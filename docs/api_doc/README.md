# ok-script API 文档

## 目录

- [Box](#box)
    - [Box.\_\_init\_\_](#box__init__)
    - [Box.area](#boxarea)
    - [Box.scale](#boxscale)
    - [Box.center](#boxcenter)
    - [Box.copy](#boxcopy)
    - [Box.crop\_frame](#boxcrop_frame)
    - [Box.center\_distance](#boxcenter_distance)
    - [Box.find\_closest\_box](#boxfind_closest_box)
- [Config](#config)
    - [Config.\_\_init\_\_](#config__init__)
    - [Config.save\_file](#configsave_file)
    - [Config.get\_default](#configget_default)
    - [Config.reset\_to\_default](#configreset_to_default)
- [BaseTask](#basetask)
    - [截图 (Screenshot)](#截图-screenshot)
        - [frame](#frame)
        - [next\_frame](#next_frame)
        - [screenshot](#screenshot)
    - [输入 (Input)](#输入-input)
        - [click](#click)
        - [click\_box](#click_box)
        - [click\_relative](#click_relative)
        - [right\_click](#right_click)
        - [middle\_click](#middle_click)
        - [swipe](#swipe)
        - [swipe\_relative](#swipe_relative)
        - [input\_text](#input_text)
        - [send\_key](#send_key)
        - [send\_key\_down](#send_key_down)
        - [send\_key\_up](#send_key_up)
        - [scroll](#scroll)
        - [scroll\_relative](#scroll_relative)
        - [mouse\_down](#mouse_down)
        - [mouse\_up](#mouse_up)
        - [move](#move)
        - [move\_relative](#move_relative)
        - [back](#back)
    - [Config 相关](#config-相关)
        - [load\_config](#load_config)
        - [validate\_config](#validate_config)
        - [get\_global\_config](#get_global_config)
    - [屏幕画图 (Screen drawing)](#屏幕画图-screen-drawing)
        - [draw\_boxes](#draw_boxes)
        - [clear\_box](#clear_box)
    - [OCR](#ocr)
        - [ocr](#ocr)
        - [wait\_ocr](#wait_ocr)
        - [wait\_click\_ocr](#wait_click_ocr)
        - [add\_text\_fix](#add_text_fix)
    - [找图 (Image finding)](#找图-image-finding)
        - [find\_feature](#find_feature)
        - [find\_one](#find_one)
        - [wait\_feature](#wait_feature)
        - [wait\_click\_feature](#wait_click_feature)
        - [get\_box\_by\_name](#get_box_by_name)
    - [找色 (Color finding)](#找色-color-finding)
        - [calculate\_color\_percentage](#calculate_color_percentage)
    - [显示信息 (Display information)](#显示信息-display-information)
        - [notification](#notification)
        - [info\_set](#info_set)
        - [info\_get](#info_get)
        - [info\_incr](#info_incr)
        - [info\_add](#info_add)
    - [日志 (Logging)](#日志-logging)
        - [log\_info](#log_info)
        - [log\_debug](#log_debug)
        - [log\_error](#log_error)
    - [其他 (Other)](#其他-other)
        - [is\_adb](#is_adb)

---

## Box

`Box` 类用于表示屏幕上的一个矩形区域，通常用于标识UI元素、图像特征等。

<a name="box__init__"></a>

### Box.\_\_init\_\_

```python
def __init__(self, x, y, width=0, height=0, confidence=1.0, name=None, to_x=-1, to_y=-1)
```

初始化一个 `Box` 对象。

- **参数:**
    - `x` (int): 矩形左上角的 x 坐标。
    - `y` (int): 矩形左上角的 y 坐标。
    - `width` (int): 矩形的宽度。如果提供了 `to_x`，则会自动计算。
    - `height` (int): 矩形的高度。如果提供了 `to_y`，则会自动计算。
    - `confidence` (float): 置信度，默认为 1.0。
    - `name` (any): 矩形的名称或标识符。
    - `to_x` (int): 矩形右下角的 x 坐标，用于计算宽度。
    - `to_y` (int): 矩形右下角的 y 坐标，用于计算高度。

<a name="boxarea"></a>

### Box.area

```python
def area(self) -> int
```

计算并返回矩形的面积。

- **返回:**
    - `int`: 矩形的面积 (width * height)。

<a name="boxscale"></a>

### Box.scale

```python
def scale(self, width_ratio: float, height_ratio: float = None)
```

按给定的宽高比缩放矩形，保持中心点不变。

- **参数:**
    - `width_ratio` (float): 宽度的缩放比例。
    - `height_ratio` (float): 高度的缩放比例，如果为 `None` 则使用 `width_ratio`。
- **返回:**
    - `Box`: 一个新的、经过缩放的 `Box` 对象。

<a name="boxcenter"></a>

### Box.center

```python
def center(self)
```

计算并返回矩形的中心点坐标。

- **返回:**
    - `tuple`: 包含中心点 (x, y) 坐标的元组。

<a name="boxcopy"></a>

### Box.copy

```python
def copy(self, x_offset=0, y_offset=0, width_offset=0, height_offset=0, name=None)
```

创建一个带有偏移量的新 `Box` 副本。

- **参数:**
    - `x_offset` (int): x 坐标的偏移量。
    - `y_offset` (int): y 坐标的偏移量。
    - `width_offset` (int): 宽度的偏移量。
    - `height_offset` (int): 高度的偏移量。
    - `name` (any): 新矩形的名称。
- **返回:**
    - `Box`: 一个新的 `Box` 对象。

<a name="boxcrop_frame"></a>

### Box.crop\_frame

```python
def crop_frame(self, frame)
```

从给定的图像帧中裁剪出矩形区域。

- **参数:**
    - `frame` (numpy.ndarray): 要裁剪的图像帧。
- **返回:**
    - `numpy.ndarray`: 裁剪后的图像区域。

<a name="boxcenter_distance"></a>

### Box.center\_distance

```python
def center_distance(self, other_box)
```

计算当前矩形与另一个矩形中心点之间的距离。

- **参数:**
    - `other_box` (Box): 另一个 `Box` 对象。
- **返回:**
    - `float`: 两个矩形中心点之间的欧几里得距离。

<a name="boxfind_closest_box"></a>

### Box.find\_closest\_box

```python
def find_closest_box(self, direction, boxes, condition=None)
```

在给定方向上查找并返回距离最近的 `Box` 对象。

- **参数:**
    - `direction` (str): 查找方向 ('up', 'down', 'left', 'right', 'all')。
    - `boxes` (list[Box]): 要在其中搜索的 `Box` 对象列表。
    - `condition` (callable, optional): 一个可选的过滤函数，用于筛选 `Box`。
- **返回:**
    - `Box` 或 `None`: 找到的最近的 `Box` 对象，如果未找到则返回 `None`。

---

## Config

`Config` 类用于管理配置文件，它继承自 `dict`，提供了从 JSON 文件加载、保存以及验证配置的功能。

<a name="config__init__"></a>

### Config.\_\_init\_\_

```python
def __init__(self, name, default, folder=None, validator=None)
```

初始化一个 `Config` 对象。

- **参数:**
    - `name` (str): 配置文件的名称（不含扩展名）。
    - `default` (dict): 默认的配置字典。
    - `folder` (str, optional): 存储配置文件的文件夹路径。
    - `validator` (callable, optional): 用于验证配置项的函数。

<a name="configsave_file"></a>

### Config.save\_file

```python
def save_file(self)
```

将当前的配置保存到 JSON 文件中。

<a name="configget_default"></a>

### Config.get\_default

```python
def get_default(self, key)
```

获取指定键的默认值。

- **参数:**
    - `key` (any): 要查询的键。
- **返回:**
    - `any`: 默认配置中对应键的值。

<a name="configreset_to_default"></a>

### Config.reset\_to\_default

```python
def reset_to_default(self)
```

将当前配置重置为默认值并保存到文件。

---

## BaseTask

`BaseTask` 是所有任务类的基类，它提供了任务执行所需的基础功能，如截图、输入、日志记录等。它继承自 `OCR`、`FindFeature` 和
`ExecutorOperation`，因此包含了这些父类的所有方法。

### 截图 (Screenshot)

<a name="frame"></a>

### frame

```python
@property
def frame(self)
```

获取当前有效的屏幕帧。此属性会确保返回的是最新的、可用的图像帧。如果脚本暂停，它会等待直到脚本恢复。

- **返回:**
    - `numpy.ndarray`: 当前的屏幕图像帧。
- **调用例子 (Calling Example):**
  ```python
  # 获取当前帧并检查其尺寸
  current_frame = self.frame
  height, width, _ = current_frame.shape
  self.log_info(f"当前屏幕分辨率为: {width}x{height}")
  ```

<a name="next_frame"></a>

### next\_frame

```python
def next_frame(self)
```

强制获取并返回一个新的屏幕帧。这会立即触发一次截图操作，而不是使用缓存的帧。

- **返回:**
    - `numpy.ndarray`: 新捕获的屏幕图像帧。
- **调用例子 (Calling Example):**
  ```python
  # 点击一个按钮后，立即获取新的屏幕内容以检查变化
  self.click(100, 100)
  new_frame = self.next_frame()
  # ... 可以在 new_frame 上进行分析 ...
  ```

<a name="screenshot"></a>

### screenshot

```python
def screenshot(self, name=None, frame=None, show_box=False, frame_box=None)
```

将当前屏幕或指定帧的图像保存到 `screenshots` 目录中，主要用于调试。保存的截图会显示在软件的UI界面中。

- **参数:**
    - `name` (str): 截图的名称，必须提供。
    - `frame` (numpy.ndarray, optional): 如果提供，则保存该帧，否则保存当前屏幕帧。
    - `show_box` (bool): 是否在截图上显示一个默认的框。
    - `frame_box` (Box, optional): 在截图上显示的特定 `Box` 区域。
- **调用例子 (Calling Example):**
  ```python
  # 当找不到某个按钮时，截取当前屏幕用于分析
  login_button = self.find_one("login_button")
  if not login_button:
      self.screenshot("login_page_error")
  ```

### 输入 (Input)

<a name="click"></a>

### click

```python
def click(self, x: int | Box | List[Box] = -1, y=-1, move_back=False, name=None, interval=-1, move=True, down_time=0.01,
          after_sleep=0, key='left')
```

在指定坐标或 `Box` 位置执行鼠标点击。坐标可以是绝对坐标（整数），也可以是相对于屏幕宽高的相对坐标（0.0到1.0之间的小数）。如果只提供了
`x` 参数且其类型为 `Box`，则会点击该 `Box` 的中心点。如果 `x` 是一个 `Box` 列表，则会点击列表中第一个 `Box` 的中心点。

- **参数:**
    - `x` (int | float | Box | list[Box]): x 坐标、相对 x 坐标或一个 `Box` 对象（或列表）。
    - `y` (int | float): y 坐标或相对 y 坐标。
    - `move_back` (bool): 点击后是否将鼠标移回原位。
    - `name` (str, optional): 点击操作的名称，用于日志记录。
    - `interval` (float): 距离上次点击的最小时间间隔（秒）。
    - `move` (bool): 是否在点击前移动鼠标。
    - `down_time` (float): 鼠标按下的持续时间（秒）。
    - `after_sleep` (float): 点击后等待的时间（秒）。
    - `key` (str): 要点击的鼠标按键 ('left', 'right', 'middle')。
- **返回:**
    - `bool`: 如果操作成功执行，返回 `True`。
- **调用例子 (Calling Example):**
  ```python
  # 1. 点击绝对坐标 (100, 150)
  self.click(100, 150)

  # 2. 点击屏幕中心（相对坐标）
  self.click(0.5, 0.5)

  # 3. 查找一个名为 "login_button" 的特征并点击它
  login_box = self.find_one("login_button")
  if login_box:
      self.click(login_box)

  # 4. 点击后等待1秒
  self.click(100, 150, after_sleep=1)
  ```

<a name="click_box"></a>

### click\_box

```python
def click_box(self, box: Box | List[Box] = None, relative_x=0.5, relative_y=0.5, raise_if_not_found=False,
              move_back=False, down_time=0.01, after_sleep=1)
```

点击一个 `Box` 对象的相对位置。

- **参数:**
    - `box` (Box | list[Box]): 要点击的 `Box` 对象或 `Box` 列表（默认点击第一个）。
    - `relative_x` (float): 相对于 `Box` 宽度的 x 坐标比例 (0.0 - 1.0)。
    - `relative_y` (float): 相对于 `Box` 高度的 y 坐标比例 (0.0 - 1.0)。
    - `raise_if_not_found` (bool): 如果 `box` 为 `None` 是否抛出异常。
    - `after_sleep` (float): 点击后等待的时间（秒）。
- **调用例子 (Calling Example):**
  ```python
  # 点击 "settings_icon" 的右上角
  settings_box = self.find_one("settings_icon")
  if settings_box:
      self.click_box(settings_box, relative_x=0.9, relative_y=0.1)
  ```

<a name="click_relative"></a>

### click\_relative

```python
def click_relative(self, x, y, move_back=False, hcenter=False, move=True, after_sleep=0, name=None, interval=-1,
                   down_time=0.02, key="left")
```

在屏幕的相对位置执行点击。

- **参数:**
    - `x` (float): 相对于屏幕宽度的 x 坐标比例 (0.0 - 1.0)。
    - `y` (float): 相对于屏幕高度的 y 坐标比例 (0.0 - 1.0)。
- **调用例子 (Calling Example):**
  ```python
  # 点击屏幕右下角区域
  self.click_relative(0.95, 0.95)
  ```

<a name="right_click"></a>

### right\_click

```python
def right_click(self, *args, **kwargs)```


执行鼠标右键点击。参数与
`click`
方法相同，但
`key`
固定为
'right'。

- ** 调用例子(Calling
Example): **
```python
# 右键点击坐标 (200, 250)
self.right_click(200, 250)
  ```

<a name="middle_click"></a>

### middle\_click

```python
def middle_click(self, *args, **kwargs)
```

执行鼠标中键点击。参数与 `click` 方法相同，但 `key` 固定为 'middle'。

- **调用例子 (Calling Example):**
  ```python
  # 中键点击屏幕中心
  self.middle_click(0.5, 0.5)
  ```

<a name="swipe"></a>

### swipe

```python
def swipe(self, from_x, from_y, to_x, to_y, duration=0.5, after_sleep=0.1, settle_time=0)
```

执行滑动操作。

- **参数:**
    - `from_x`, `from_y` (int): 滑动起点的绝对坐标。
    - `to_x`, `to_y` (int): 滑动终点的绝对坐标。
    - `duration` (float): 滑动持续时间（毫秒）。
    - `after_sleep` (float): 滑动后等待的时间（秒）。
    - `settle_time` (float): 到达终点后，在松开手指前停留的时间（秒）。
- **调用例子 (Calling Example):**
  ```python
  # 从 (200, 800) 滑动到 (200, 200) 来向上滚动列表
  self.swipe(200, 800, 200, 200, duration=500)
  ```

<a name="swipe_relative"></a>

### swipe\_relative```python

def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0)

```
在屏幕的相对位置之间执行滑动操作。

- **参数:**
  - `from_x`, `from_y` (float): 滑动起点的相对坐标 (0.0 - 1.0)。
  - `to_x`, `to_y` (float): 滑动终点的相对坐标 (0.0 - 1.0)。
- **调用例子 (Calling Example):**
  ```python
  # 从屏幕中心向上滑动半个屏幕
  self.swipe_relative(0.5, 0.75, 0.5, 0.25)
  ```

<a name="input_text"></a>

### input\_text

```python
def input_text(self, text)
```

输入指定的文本。

- **参数:**
    - `text` (str): 要输入的字符串。
- **调用例子 (Calling Example):**
  ```python
  # 在输入框中输入用户名
  self.click(username_field_box)
  self.input_text("my_username")
  ```

<a name="send_key"></a>

### send\_key

```python
def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0)
```

模拟按下并释放一个键盘按键。

- **参数:**
    - `key` (str): 要发送的按键（例如 'a', 'enter', 'f1'）。
    - `down_time` (float): 按键按下的持续时间（秒）。
    - `interval` (float): 距离上次按键的最小时间间隔（秒）。
    - `after_sleep` (float): 按键后等待的时间（秒）。
- **调用例子 (Calling Example):**
  ```python
  # 发送 Enter 键确认操作
  self.send_key('enter')
  ```

<a name="send_key_down"></a>

### send\_key\_down

```python
def send_key_down(self, key)
```

模拟按下键盘按键（不释放）。

- **调用例子 (Calling Example):**
  ```python
  # 按下 Shift 键
  self.send_key_down('shift')
  ```

<a name="send_key_up"></a>

### send\_key\_up

```python
def send_key_up(self, key)
```

模拟释放键盘按键。

- **调用例子 (Calling Example):**
  ```python
  # 释放 Shift 键
  self.send_key_up('shift')
  ```

<a name="scroll"></a>

### scroll

```python
def scroll(self, x, y, count)
```

在指定坐标位置执行鼠标滚轮滚动。

- **参数:**
    - `x`, `y` (int): 滚动的绝对坐标。
    - `count` (int): 滚动量，正数向上，负数向下。
- **调用例子 (Calling Example):**
  ```python
  # 在坐标 (500, 500) 处向上滚动 5 个单位
  self.scroll(500, 500, 5)
  ```

<a name="scroll_relative"></a>

### scroll\_relative

```python
def scroll_relative(self, x, y, count)
```

在屏幕的相对位置执行鼠标滚轮滚动。

- **参数:**
    - `x`, `y` (float): 滚动的相对坐标 (0.0 - 1.0)。
- **调用例子 (Calling Example):**
  ```python
  # 在屏幕中心向下滚动 10 个单位
  self.scroll_relative(0.5, 0.5, -10)
  ```

<a name="mouse_down"></a>

### mouse\_down

```python
def mouse_down(self, x=-1, y=-1, name=None, key="left")
```

在指定位置按下鼠标按键（不释放）。

- **调用例子 (Calling Example):**
  ```python
  # 在 (100, 100) 按下鼠标左键，用于拖拽操作的开始
  self.mouse_down(100, 100)
  ```

<a name="mouse_up"></a>

### mouse\_up```python

def mouse_up(self, name=None, key="left")

```
释放鼠标按键。

- **调用例子 (Calling Example):**
  ```python
  # 移动到 (300, 300) 后释放鼠标左键，完成拖拽
  self.move(300, 300)
  self.mouse_up()
  ```

<a name="move"></a>

### move```python

def move(self, x, y)

```
将鼠标移动到指定的绝对坐标。

- **调用例子 (Calling Example):**
  ```python
  # 将鼠标移动到 (500, 500)
  self.move(500, 500)
  ```

<a name="move_relative"></a>

### move\_relative

```python
def move_relative(self, x, y)
```

将鼠标移动到指定的相对坐标。

- **调用例子 (Calling Example):**
  ```python
  # 将鼠标移动到屏幕的左上角
  self.move_relative(0, 0)
  ```

<a name="back"></a>

### back

```python
def back(self, after_sleep=0)
```

模拟返回操作，通常是发送 'esc' 键（PC）或返回键（Android）。

- **调用例子 (Calling Example):**
  ```python
  # 关闭一个弹窗
  self.back(after_sleep=0.5)
  ```

### Config 相关

<a name="load_config"></a>

### load\_config

```python
def load_config(self)


    ```加载当前任务的配置文件。通常在任务初始化时自动调用。

< a
name = "validate_config" > < / a >
### validate\_config
```python


def validate_config(self, key, value)
```

验证一个配置项是否合法。子类可以重写此方法以实现自定义验证逻辑。

- **返回:**
    - `str` 或 `None`: 如果验证失败，返回错误信息字符串；否则返回 `None`。
- **调用例子 (Calling Example):**
  ```python
  # 在任务子类中实现
  def validate_config(self, key, value):
      if key == 'Retry Count' and not (0 < value <= 10):
          return "Retry Count must be between 1 and 10."
      return None
  ```

<a name="get_global_config"></a>

### get\_global\_config

```python
def get_global_config(self, option)
```

获取一个全局配置对象。

- **参数:**
    - `option` (ConfigOption): 全局配置选项的定义。
- **返回:**
    - `Config`: 对应的全局 `Config` 对象。
- **调用例子 (Calling Example):**
  ```python
  # 获取基本设置
  basic_settings = self.get_global_config(basic_options)
  if basic_settings.get('Mute Game while in Background'):
      self.log_info("游戏将在后台静音。")
  ```

### 屏幕画图 (Screen drawing)

<a name="draw_boxes"></a>

### draw\_boxes

```python
def draw_boxes(feature_name=None, boxes=None, color="red", debug=True)
```

在屏幕上绘制一个或多个 `Box`，用于调试。

- **参数:**
    - `feature_name` (str, optional): 绘制的特征名称。
    - `boxes` (list[Box] | Box): 要绘制的 `Box` 对象或列表。
    - `color` (str): 绘制框的颜色。
    - `debug` (bool): 是否仅在调试模式下绘制。
- **调用例子 (Calling Example):**
  ```python
  # 找到所有按钮并用绿色框标出
  all_buttons = self.find_feature("buttons")
  self.draw_boxes("Found Buttons", all_buttons, color="green")
  ```

<a name="clear_box"></a>

### clear\_box

```python
def clear_box(self)
```

清除屏幕上所有由 `draw_boxes` 绘制的框。

- **调用例子 (Calling Example):**
  ```python
  # 进入新场景前清除旧的标记框
  self.clear_box()
  ```

### OCR

<a name="ocr"></a>

### ocr

```python
def ocr(self, x=0, y=0, to_x=1, to_y=1, match=None, width=0, height=0, box=None, threshold=0, frame=None,
        target_height=0, use_grayscale=False, log=False, lib='default')
```

对屏幕指定区域进行光学字符识别（OCR）。

- **参数:**
    - `x`, `y`, `to_x`, `to_y` (float): 区域的相对坐标。
    - `match` (str | re.Pattern | list): 用于匹配识别结果的字符串或正则表达式。
    - `box` (Box, optional): 指定一个 `Box` 对象作为识别区域。
    - `threshold` (float): 识别结果的置信度阈值。
    - `target_height` (int): 识别前将图像缩放到的目标高度，可以提高识别准确率。
- **返回:**
    - `list[Box]`: 包含识别结果的 `Box` 对象列表，`Box.name` 为识别出的文本。
- **调用例子 (Calling Example):**
  ```python
  # 识别屏幕上半部分所有包含 "确定" 或 "取消" 的文本
  action_texts = self.ocr(to_y=0.5, match=["确定", "取消"])
  for box in action_texts:
      self.log_info(f"找到文本: {box.name} at {box.center()}")
  ```

<a name="wait_ocr"></a>

### wait\_ocr

```python
def wait_ocr(self, ..., time_out=0, raise_if_not_found=False, settle_time=-1)
```

等待直到在指定区域内 OCR 识别到匹配的文本。参数与 `ocr` 类似。

- **参数:**
    - `time_out` (int): 等待的超时时间（秒）。
    - `raise_if_not_found` (bool): 如果超时仍未找到，是否抛出异常。
    - `settle_time` (float): 找到后额外等待的时间（秒），确保界面稳定。
- **返回:**
    - `list[Box]` 或 `None`: 找到的文本 `Box` 列表，或在超时后返回 `None`。
- **调用例子 (Calling Example):**
  ```python
  # 等待10秒，直到屏幕上出现 "加载完成"
  loading_text = self.wait_ocr(match="加载完成", time_out=10)
  if loading_text:
      self.log_info("游戏加载完成！")
  ```

<a name="wait_click_ocr"></a>

### wait\_click\_ocr

```python
def wait_click_ocr(self, ..., time_out=0, raise_if_not_found=False, after_sleep=0, settle_time=-1)
```

等待直到 OCR 识别到匹配的文本，并点击第一个找到的结果。

- **返回:**
    - `Box` 或 `None`: 被点击的 `Box` 对象，如果未找到则返回 `None`。
- **调用例子 (Calling Example):**
  ```python
  # 等待并点击 "开始游戏" 按钮
  self.wait_click_ocr(match="开始游戏", time_out=5, raise_if_not_found=True)
  ```

<a name="add_text_fix"></a>

### add\_text\_fix

```python
def add_text_fix(self, fix)
```

添加 OCR 文本修正规则。用于修正 OCR 引擎常见的识别错误。

- **参数:**
    - `fix` (dict): 一个字典，键为错误文本，值为正确文本。
- **调用例子 (Calling Example):**
  ```python
  # 将常见的 "lv1" OCR 错误修正为 "Lv1"
  self.add_text_fix({"lv1": "Lv1", "g0ld": "gold"})
  ```

### 找图 (Image finding)

<a name="find_feature"></a>

### find\_feature

```python
def find_feature(self, feature_name=None, box=None, threshold=0, ...) -> List[Box]
```

在指定区域内查找一个或多个图像特征。

- **参数:**
    - `feature_name` (str | list[str]): 要查找的特征名称（在 COCO 文件中定义）。
    - `box` (Box | str, optional): 在该 `Box` 区域内进行搜索。
    - `threshold` (float): 匹配的置信度阈值。
    - `horizontal_variance`, `vertical_variance` (float): 在特征原始位置附近扩大的搜索范围比例。
- **返回:**
    - `list[Box]`: 找到的所有匹配特征的 `Box` 对象列表。
- **调用例子 (Calling Example):**
  ```python
  # 查找屏幕上所有的 "coin" 图标
  coins = self.find_feature("coin", threshold=0.9)
  self.log_info(f"找到了 {len(coins)} 个金币图标。")
  ```

<a name="find_one"></a>

### find\_one

```python
def find_one(self, feature_name=None, ...) -> Box
```

查找单个图像特征，并返回置信度最高的一个。参数与 `find_feature` 相同。

- **返回:**
    - `Box` 或 `None`: 找到的置信度最高的 `Box` 对象，如果未找到则返回 `None`。
- **调用例子 (Calling Example):**
  ```python
  # 查找设置按钮
  settings_button = self.find_one("settings_button")
  if settings_button:
      self.click(settings_button)
  ```

<a name="wait_feature"></a>

### wait\_feature

```python
def wait_feature(self, feature, time_out=0, raise_if_not_found=False, settle_time=-1, ...)
```

等待直到在屏幕上找到指定的图像特征。

- **参数:**
    - `feature` (str): 要等待的特征名称。
    - `time_out` (int): 等待的超时时间（秒）。
    - `raise_if_not_found` (bool): 超时后是否抛出异常。
    - `settle_time` (float): 找到后额外等待的时间（秒）。
- **返回:**
    - `Box` 或 `None`: 找到的 `Box` 对象。
- **调用例子 (Calling Example):**
  ```python
  # 等待加载界面消失（通过查找主界面 logo）
  main_menu_logo = self.wait_feature("main_menu_logo", time_out=30)
  if not main_menu_logo:
      self.log_error("加载超时！")
  ```

<a name="wait_click_feature"></a>

### wait\_click\_feature

```python
def wait_click_feature(self, feature, time_out=0, raise_if_not_found=True, after_sleep=0, ...)
```

等待直到找到指定的图像特征，并对其进行点击。

- **返回:**
    - `bool`: 如果成功找到并点击，返回 `True`。
- **调用例子 (Calling Example):**
  ```python
  # 等待并点击 "跳过" 按钮
  self.wait_click_feature("skip_button", time_out=5, raise_if_not_found=False, after_sleep=1)
  ```

<a name="get_box_by_name"></a>

### get\_box\_by\_name

```python
def get_box_by_name(self, name)
```

根据名称获取一个预定义的 `Box`。名称可以是在 COCO 文件中定义的 `box_` 前缀的特征，也可以是 'left', 'right', 'top', '
bottom' 等预设区域。

- **参数:**
    - `name` (str): `Box` 的名称。
- **返回:**
    - `Box`: 对应的 `Box` 对象。
- **调用例子 (Calling Example):**
  ```python
  # 在屏幕右半部分查找敌人
  right_half = self.get_box_by_name("right")
  enemies = self.find_feature("enemy_icon", box=right_half)
  ```

### 找色 (Color finding)

<a name="calculate_color_percentage"></a>

### calculate\_color\_percentage```python

def calculate_color_percentage(self, color, box: Box | str)

```
计算指定 `Box` 区域内特定颜色的像素百分比。

- **参数:**
  - `color` (dict): 颜色范围字典，格式为 `{'r': (min, max), 'g': (min, max), 'b': (min, max)}`。
  - `box` (Box | str): 要计算的 `Box` 对象或其名称。
- **返回:**
  - `float`: 颜色像素所占的百分比 (0.0 - 1.0)。
- **调用例子 (Calling Example):**
  ```python
  # 定义红色范围
  red_color = {'r': (200, 255), 'g': (0, 100), 'b': (0, 100)}
  health_bar_box = self.find_one("health_bar")
  if health_bar_box:
      # 检查生命条中的红色（低血量）百分比
      low_health_percentage = self.calculate_color_percentage(red_color, health_bar_box)
      if low_health_percentage > 0.5:
          self.log_info("血量危险！")
  ```

### 显示信息 (Display information)

<a name="notification"></a>

### notification

```python
def notification(self, message, title=None, error=False, tray=False, show_tab=None)
```

在主界面显示一个通知信息条或系统托盘通知。

- **参数:**
    - `message` (str): 通知内容。
    - `title` (str, optional): 通知标题。
    - `error` (bool): 是否为错误通知。
    - `tray` (bool): 是否同时显示系统托盘通知。
- **调用例子 (Calling Example):**
  ```python
  # 任务完成后发送一个成功的托盘通知
  self.notification("每日任务已完成", "任务成功", tray=True)
  ```

<a name="info_set"></a>

### info\_set

```python
def info_set(self, key, value)```


在任务的监控信息中设置一个键值对。

- ** 调用例子(Calling
Example): **
```python
# 设置当前状态
self.info_set("当前状态", "正在寻找副本入口")
  ```

<a name="info_get"></a>

### info\_get

```python
def info_get(self, *args, **kwargs)
```

从任务的监控信息中获取一个值。

- **调用例子 (Calling Example):**
  ```python
  # 获取已完成次数
  completed_runs = self.info_get("已完成次数", 0)
  ```

<a name="info_incr"></a>

### info\_incr

```python
def info_incr(self, key, inc=1)
```

将任务监控信息中的一个数值增加指定的值。

- **调用例子 (Calling Example):**
  ```python
  # 将金币计数器加100
  self.info_incr("金币", 100)
  ```

<a name="info_add"></a>

### info\_add

```python
def info_add(self, key, count=1)
```

同 `info_incr`。

### 日志 (Logging)

<a name="log_info"></a>

### log\_info

```python
def log_info(self, message, notify=False)
```

记录一条信息级别的日志。

- **参数:**
    - `message` (str): 日志内容。
    - `notify` (bool): 是否同时通过 `notification` 显示通知。
- **调用例子 (Calling Example):**
  ```python
  self.log_info("任务开始执行。")
  ```

<a name="log_debug"></a>

### log\_debug```python

def log_debug(self, message, notify=False)

```
记录一条调试级别的日志。

- **调用例子 (Calling Example):**
  ```python
  button_pos = self.find_one("some_button")
  self.log_debug(f"按钮坐标: {button_pos}")
  ```

<a name="log_error"></a>

### log\_error

```python
def log_error(self, message, exception=None, notify=False)
```

记录一条错误级别的日志。

- **参数:**
    - `exception` (Exception, optional): 关联的异常对象。
- **调用例子 (Calling Example):**
  ```python
  try:
      # ... some operation that might fail ...
  except Exception as e:
      self.log_error("关键操作失败，任务终止。", e, notify=True)
  ```

### 其他 (Other)

<a name="is_adb"></a>

### is\_adb

```python
def is_adb(self) -> bool
```

判断当前是否正在通过 ADB 控制安卓设备。

- **返回:**
    - `bool`: 如果是安卓设备，返回 `True`；如果是 PC 窗口，返回 `False`。
- **调用例子 (Calling Example):**
  ```python
  if self.is_adb():
      self.log_info("当前为安卓模式，将使用返回键。")
      self.back()
  else:
      self.log_info("当前为PC模式，将使用ESC键。")
      self.send_key('esc')
  ```