# ok-script API 文档

## 目录

- [Box](#box)
    - [Box.\_\_init\_\_](#box__init__)
    - [Box.area](#boxarea)
    - [Box.in\_boundary](#boxin_boundary)
    - [Box.scale](#boxscale)
    - [Box.center](#boxcenter)
    - [Box.copy](#boxcopy)
    - [Box.crop\_frame](#boxcrop_frame)
    - [Box.center\_distance](#boxcenter_distance)
    - [Box.closest\_distance](#boxclosest_distance)
    - [Box.relative\_with\_variance](#boxrelative_with_variance)
    - [Box.find\_closest\_box](#boxfind_closest_box)
- [BaseTask](#basetask)
    - [截图 (Screenshot)](#截图-screenshot)
        - [frame](#frame)
        - [next\_frame](#next_frame)
        - [screenshot](#screenshot)
        - [adb\_ui\_dump](#adb_ui_dump)
    - [输入 (Input)](#输入-input)
        - [click](#click)
        - [click\_box](#click_box)
        - [click\_box\_if\_name\_match](#click_box_if_name_match)
        - [click\_relative](#click_relative)
        - [wait\_click\_box](#wait_click_box)
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
        - [get\_global\_config\_desc](#get_global_config_desc)
    - [任务配置 (Task Configuration)](#任务配置-task-configuration)
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
        - [get\_feature\_by\_name](#get_feature_by_name)
        - [feature\_exists](#feature_exists)
        - [find\_feature\_and\_set](#find_feature_and_set)
        - [find\_best\_match\_in\_box](#find_best_match_in_box)
        - [find\_first\_match\_in\_box](#find_first_match_in_box)
    - [找色 (Color finding)](#找色-color-finding)
        - [calculate\_color\_percentage](#calculate_color_percentage)
    - [显示信息 (Display information)](#显示信息-display-information)
        - [notification](#notification)
        - [info\_set](#info_set)
        - [info\_get](#info_get)
        - [info\_incr](#info_incr)
        - [info\_add](#info_add)
        - [info\_add\_to\_list](#info_add_to_list)
        - [info\_clear](#info_clear)
    - [日志 (Logging)](#日志-logging)
        - [log\_info](#log_info)
        - [log\_debug](#log_debug)
        - [log\_error](#log_error)
    - [其他 (Other)](#其他-other)
        - [is\_adb](#is_adb)
        - [is\_browser](#is_browser)
        - [adb\_shell](#adb_shell)
        - [ensure\_in_front](#ensure_in_front)
        - [box\_of_screen](#box_of_screen)
        - [box\_of_screen\_scaled](#box_of_screen_scaled)
        - [screen\_width](#screen_width)
        - [screen\_height](#screen_height)
        - [width\_of_screen](#width_of_screen)
        - [wait\_until](#wait_until)
        - [wait\_scene](#wait_scene)
        - [sleep](#sleep)
        - [sleep_check](#sleep_check)
        - [run\_task\_by\_class](#run_task_by_class)
        - [tr](#tr)
        - [should\_trigger](#should_trigger)
        - [go\_to\_tab](#go_to_tab)
        - [find\_boxes](#find_boxes)


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

<a name="boxin_boundary"></a>

### Box.in\_boundary

```python
def in_boundary(self, boxes) -> list[Box]
```

返回一个列表，其中包含传入参数 `boxes` 中所有位于当前 `Box` 边界内的 `Box` 对象。

- **参数:**
    - `boxes` (list[Box]): 要检查的 `Box` 对象列表。
- **返回:**
    - `list[Box]`: 位于边界内的 `Box` 列表。

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
def center_distance(self, other_box) -> float
```

计算当前矩形与另一个矩形中心点之间的距离。

- **参数:**
    - `other_box` (Box): 另一个 `Box` 对象。
- **返回:**
    - `float`: 两个矩形中心点之间的欧几里得距离。

<a name="boxclosest_distance"></a>

### Box.closest\_distance

```python
def closest_distance(self, Box other) -> float
```

计算两个矩形边界之间的最短距离。如果两个矩形相交，则距离为 0。

- **参数:**
    - `other` (Box): 另一个 `Box` 对象。
- **返回:**
    - `float`: 两个矩形之间的最短距离。

<a name="boxrelative_with_variance"></a>

### Box.relative\_with\_variance

```python
def relative_with_variance(self, relative_x=0.5, relative_y=0.5) -> tuple[int, int]
```

返回矩形内的一个坐标点。支持相对位置并带有微小的随机偏移，模拟真实的人工点击。

- **参数:**
    - `relative_x` (float): 相对 x 坐标 (0.0 - 1.0)。
    - `relative_y` (float): 相对 y 坐标 (0.0 - 1.0)。
- **返回:**
    - `tuple[int, int]`: 计算出的 (x, y) 坐标。

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

<a name="next_frame"></a>

### next\_frame

```python
def next_frame(self)
```

强制获取并返回一个新的屏幕帧。这会立即触发一次截图操作，而不是使用缓存的帧。

- **返回:**
    - `numpy.ndarray`: 新捕获的屏幕图像帧。

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

<a name="adb_ui_dump"></a>

### adb\_ui\_dump

```python
def adb_ui_dump(self) -> str
```

通过 ADB 获取当前屏幕的 UI 层级结构 XML 字符串（仅限安卓/模拟器模式）。

- **返回:**
    - `str`: UI 结构的 XML 字符串。

### 输入 (Input)

<a name="click"></a>

### click

```python
def click(self, x: int | Box | List[Box] = -1, y=-1, move_back=False, name=None, interval=-1, move=True, down_time=0.01,
          after_sleep=0, key='left', hcenter=False, vcenter=False)
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
    - `hcenter`, `vcenter` (bool): 如果点击相对坐标且设为 True，则以屏幕中心为原点。
- **返回:**
    - `bool`: 如果操作成功执行，返回 `True`。

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

<a name="click_box_if_name_match"></a>

### click\_box\_if\_name\_match

```python
def click_box_if_name_match(self, boxes, names, relative_x=0.5, relative_y=0.5)
```

在 `Box` 列表中查找名称匹配的第一个 `Box` 并点击。

- **参数:**
    - `boxes` (list[Box]): `Box` 列表。
    - `names` (str | list[str] | re.Pattern): 要匹配的名称或模式。

<a name="click_relative"></a>

### click\_relative

```python
def click_relative(self, x, y, move_back=False, hcenter=False, vcenter=False, move=True, after_sleep=0, name=None, interval=-1,
                   down_time=0.02, key="left")
```

在屏幕的相对位置执行点击。

- **参数:**
    - `x` (float): 相对于屏幕宽度的 x 坐标比例 (0.0 - 1.0)。
    - `y` (float): 相对于屏幕高度的 y 坐标比例 (0.0 - 1.0)。

<a name="wait_click_box"></a>

### wait\_click\_box

```python
def wait_click_box(self, condition, time_out=0, pre_action=None, post_action=None, raise_if_not_found=False)
```

等待一个返回 `Box` 的条件函数成立，并点击该 `Box`。

- **参数:**
    - `condition` (callable): 返回 `Box` 或 `list[Box]` 的函数。

<a name="right_click"></a>

### right\_click

```python
def right_click(self, *args, **kwargs)
```

执行鼠标右键点击。参数与 `click` 方法相同，但 `key` 固定为 'right'。

<a name="middle_click"></a>

### middle\_click

```python
def middle_click(self, *args, **kwargs)
```

执行鼠标中键点击。参数与 `click` 方法相同，但 `key` 固定为 'middle'。

<a name="swipe"></a>

### swipe

```python
def swipe(self, from_x, from_y, to_x, to_y, duration=0.5, after_sleep=0.1, settle_time=0)
```

执行滑动操作。

- **参数:**
    - `from_x`, `from_y` (int): 滑动起点的绝对坐标。
    - `to_x`, `to_y` (int): 滑动终点的绝对坐标。
    - `duration` (float): 滑动持续时间（秒）。
    - `after_sleep` (float): 滑动后等待的时间（秒）。
    - `settle_time` (float): 到达终点后，在松开手指前停留的时间（秒）。

<a name="swipe_relative"></a>

### swipe\_relative

```python
def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0)
```

在屏幕的相对位置之间执行滑动操作。

- **参数:**
    - `from_x`, `from_y` (float): 滑动起点的相对坐标 (0.0 - 1.0)。
    - `to_x`, `to_y` (float): 滑动终点的相对坐标 (0.0 - 1.0)。

<a name="input_text"></a>

### input\_text

```python
def input_text(self, text)
```

输入指定的文本。

- **参数:**
    - `text` (str): 要输入的字符串。

<a name="send_key"></a>

### send\_key

```python
def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0)
```

模拟按下并释放一个键盘按键。

- **参数:**
    - `key` (str): 要发送的按键（例如 'a', 'enter', 'f1'）。

<a name="send_key_down"></a>

### send_key_down

```python
def send_key_down(self, key)
```

模拟按下键盘按键（不释放）。

<a name="send_key_up"></a>

### send_key_up

```python
def send_key_up(self, key)
```

模拟释放键盘按键。

<a name="scroll"></a>

### scroll

```python
def scroll(self, x, y, count)
```

在指定坐标位置执行鼠标滚轮滚动。

- **参数:**
    - `x`, `y` (int): 滚动的绝对坐标。
    - `count` (int): 滚动量，正数向上，负数向下。

<a name="scroll_relative"></a>

### scroll\_relative

```python
def scroll_relative(self, x, y, count)
```

在屏幕的相对位置执行鼠标滚轮滚动。

- **参数:**
    - `x`, `y` (float): 滚动的相对坐标 (0.0 - 1.0)。

<a name="mouse_down"></a>

### mouse\_down

```python
def mouse_down(self, x=-1, y=-1, name=None, key="left")
```

在指定位置按下鼠标按键（不释放）。

<a name="mouse_up"></a>

### mouse\_up

```python
def mouse_up(self, name=None, key="left")
```

释放鼠标按键。

<a name="move"></a>

### move

```python
def move(self, x, y)
```

将鼠标移动到指定的绝对坐标。

<a name="move_relative"></a>

### move\_relative

```python
def move_relative(self, x, y)
```

将鼠标移动到指定的相对坐标。

<a name="back"></a>

### back

```python
def back(self, *args, **kwargs)
```

模拟返回操作，通常是发送 'esc' 键（PC）或返回键（Android）。支持 `after_sleep` 参数。

### Config 相关

<a name="load_config"></a>

### load\_config

```python
def load_config(self)
```

加载当前任务的配置文件。通常在任务初始化时自动调用。

<a name="validate_config"></a>

### validate\_config

```python
def validate_config(self, key, value)
```

验证一个配置项是否合法。子类可以重写此方法以实现自定义验证逻辑。

- **返回:**
    - `str` 或 `None`: 如果验证失败，返回错误信息字符串；否则返回 `None`。

<a name="get_global_config"></a>

### get\_global\_config

```python
def get_global_config(self, option)
```

获取一个全局配置对象的值。

- **参数:**
    - `option` (ConfigOption): 全局配置选项的定义。

<a name="get_global_config_desc"></a>

### get\_global\_config\_desc

```python
def get_global_config_desc(self, option) -> str
```

获取一个全局配置选项的描述。

---

### 任务配置 (Task Configuration)

`BaseTask` 允许通过 `default_config` 和 `config_type` 来定义任务在 GUI 界面中的配置表单。

#### 默认配置 (self.default_config)

在 `__init__` 中定义 `self.default_config`。框架会根据值的 Python 类型自动推断 GUI 控件：

- `bool`: 开关按钮 (SwitchButton)
- `int`: 整数输入框 (SpinBox)
- `float`: 浮点数输入框 (DoubleSpinBox)
- `list`: 列表修改项 (ModifyListItem)
- `str`: 
    - 长度 > 16 或包含 `\n`: 多行文本框 (TextEdit)
    - 其他情况: 单行文本框 (LineEdit)

#### 显示指定配置类型 (self.config_type)

如果需要更复杂的控件（如下拉菜单、多选框或按钮），可以使用 `self.config_type` 进行显式定义。

目前支持以下类型：

- **`drop_down`**: 下拉选择框。
    - **参数:** `options` (list[str]): 选项列表。
- **`multi_selection`**: 多选列表。
    - **参数:** `options` (list[str]): 选项列表。
- **`text_edit`**: 强制使用多行文本框。
- **`global`**: 引用全局配置项。
- **`button` (NEW)**: 在配置区域显示一个或多个按钮，用于触发特定方法。
    - **参数:**
        - `text` (str): 按钮上显示的文本（该文本会参与 `og.app.tr` 翻译）。
        - `icon` (FluentIcon): 可选图标。
        - `callback` (callable): 点击按钮时触发的函数或方法。
        - `buttons` (list[dict]): 如果需要显示多个按钮，可以提供一个按钮配置列表，每个元素包含上述 `text`, `icon`, `callback`。
    - **注意:** `button` 类型的配置项其 key 和 value 只用于 GUI 渲染展示，**不会** 被保存到本地配置文件中。

**示例代码:**

```python
class MyTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {
            'Run Count': 1,
            'Mode': 'Default',
            'Advanced Tool': 'Action' # 占位符
        }
        self.config_type = {
            'Mode': {
                'type': 'drop_down', 
                'options': ['Default', 'Fast']
            },
            'Advanced Tool': {
                'type': 'button',
                'buttons': [
                    {
                        'text': 'Run Diagnosis',
                        'icon': FluentIcon.SEARCH,
                        'callback': self.run_diagnosis
                    },
                    {
                        'text': 'Clean Cache',
                        'icon': FluentIcon.DELETE,
                        'callback': self.clean_cache
                    }
                ]
            }
        }
        self.config_description = {
            'Advanced Tool': 'Click to run advanced operations'
        }

    def run_diagnosis(self):
        self.log_info("Starting diagnosis...")
```

---

### 屏幕画图 (Screen drawing)

<a name="draw_boxes"></a>

### draw\_boxes

```python
def draw_boxes(feature_name=None, boxes=None, color="red", debug=True)
```

在屏幕上绘制一个或多个 `Box`，用于调试。

- **参数:**
    - `feature_name` (str, optional): 绘制的图层名称。
    - `boxes` (list[Box] | Box): 要绘制的 `Box` 对象或列表。

<a name="clear_box"></a>

### clear\_box

```python
def clear_box(self)
```

清除屏幕上由 `draw_boxes` 绘制的所有框。

### OCR

<a name="ocr"></a>

### ocr

```python
def ocr(self, x=0, y=0, to_x=1, to_y=1, match=None, width=0, height=0, box=None, threshold=0, frame=None,
        target_height=0, use_grayscale=False, log=False, frame_processor=None, lib='default')
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

<a name="wait_ocr"></a>

### wait\_ocr

```python
def wait_ocr(self, ..., time_out=0, raise_if_not_found=False, settle_time=-1)
```

等待直到在指定区域内 OCR 识别到匹配的文本。参数与 `ocr` 类似。

- **返回:**
    - `list[Box]` 或 `None`: 找到的文本 `Box` 列表，或在超时后返回 `None`。

<a name="wait_click_ocr"></a>

### wait\_click\_ocr

```python
def wait_click_ocr(self, ..., time_out=0, raise_if_not_found=False, after_sleep=0, settle_time=-1)
```

等待直到 OCR 识别到匹配的文本，并点击第一个找到的结果。参数与 `ocr` 类似。

- **返回:**
    - `Box` 或 `None`: 被点击的 `Box` 对象，如果未找到则返回 `None`。

<a name="add_text_fix"></a>

### add\_text\_fix

```python
def add_text_fix(self, fix)
```

添加 OCR 文本修正规则。用于修正 OCR 引擎常见的识别错误。

- **参数:**
    - `fix` (dict): 一个字典，键为错误文本，值为正确文本。

### 找图 (Image finding)

<a name="find_feature"></a>

### find\_feature

```python
def find_feature(self, feature_name=None, box=None, threshold=0, ...) -> List[Box]
```

在指定区域内查找一个或多个图像特征。

- **参数:**
    - `feature_name` (str | list[str]): 要查找的特征名称。
    - `box` (Box | str, optional): 在该 `Box` 区域内进行搜索。
    - `threshold` (float): 匹配的置信度阈值。
- **返回:**
    - `list[Box]`: 找到的所有匹配特征的 `Box` 对象列表。

<a name="find_one"></a>

### find\_one

```python
def find_one(self, feature_name=None, ...) -> Box
```

查找单个图像特征，并返回置信度最高的一个。参数与 `find_feature` 相同。

- **返回:**
    - `Box` 或 `None`: 找到的置信度最高的 `Box` 对象，如果未找到则返回 `None`。

<a name="wait_feature"></a>

### wait\_feature

```python
def wait_feature(self, feature, time_out=0, raise_if_not_found=False, settle_time=-1, ...)
```

等待直到在屏幕上找到指定的图像特征。

- **参数:**
    - `feature` (str): 要等待的特征名称。
    - `time_out` (int): 等待的超时时间（秒）。
- **返回:**
    - `Box` 或 `None`: 找到的 `Box` 对象。

<a name="wait_click_feature"></a>

### wait\_click\_feature

```python
def wait_click_feature(self, feature, time_out=0, raise_if_not_found=True, after_sleep=0, ...)
```

等待直到找到指定的图像特征，并对其进行点击。

- **返回:**
    - `bool`: 如果成功找到并点击，返回 `True`。

<a name="get_box_by_name"></a>

### get\_box\_by\_name

```python
def get_box_by_name(self, name) -> Box
```

根据名称获取一个预定义的 `Box`。名称可以是定义的特征名，也可以是内置预设区域。

- **可选预设名称:**
    - `top`, `bottom`, `left`, `right`
    - `top_left`, `top_right`, `bottom_left`, `bottom_right`
- **返回:**
    - `Box`: 对应的 `Box` 对象。

<a name="get_feature_by_name"></a>

### get\_feature\_by\_name

```python
def get_feature_by_name(self, name)
```

根据名称获取特性的详细定义和原始图像。

<a name="feature_exists"></a>

### feature\_exists

```python
def feature_exists(self, feature_name: str) -> bool
```

检查指定的特征名称是否在已加载的任务特征集中。

<a name="find_feature_and_set"></a>

### find\_feature\_and\_set

```python
def find_feature_and_set(self, features, threshold=0) -> bool
```

查找多个特征并将结果作为同名属性设置到当前任务对象中。

- **参数:**
    - `features` (str | list[str]): 要查找的特征名称。
- **返回:**
    - `bool`: 是否所有指定的特征都找到了。

<a name="find_best_match_in_box"></a>

### find\_best\_match\_in\_box

```python
def find_best_match_in_box(self, box, to_find, threshold) -> Box
```

在给定的 `Box` 内寻找 `to_find` 列表中置信度最高的一个特征。

<a name="find_first_match_in_box"></a>

### find\_first\_match\_in\_box

```python
def find_first_match_in_box(self, box, to_find, threshold) -> Box
```

在给定的 `Box` 内寻找 `to_find` 列表中第一个匹配的特征。

### 找色 (Color finding)

<a name="calculate_color_percentage"></a>

### calculate\_color\_percentage

```python
def calculate_color_percentage(self, color, box: Box | str) -> float
```

计算指定 `Box` 区域内特定颜色的像素百分比。

- **参数:**
  - `color` (dict): 颜色范围字典，格式为 `{'r': (min, max), 'g': (min, max), 'b': (min, max)}`。
  - `box` (Box | str): 要计算的 `Box` 对象或其名称。
- **返回:**
  - `float`: 颜色像素所占的百分比 (0.0 - 1.0)。

### 显示信息 (Display information)

<a name="notification"></a>

### notification

```python
def notification(self, message, title=None, error=False, tray=False, show_tab=None)
```

在主界面显示一个通知信息条或系统托盘通知。

- **参数:**
    - `message` (str): 通知内容。
    - `tray` (bool): 是否同时显示系统托盘通知。
    - `show_tab` (str): 点击通知时跳转到的 UI 选项卡。

<a name="info_set"></a>

### info\_set

```python
def info_set(self, key, value)
```

在任务的监控信息中设置一个键值对（会显示在 UI 的任务卡片中）。

<a name="info_get"></a>

### info\_get

```python
def info_get(self, key, default=None)
```

从任务的监控信息中获取一个值。

<a name="info_incr"></a>

### info\_incr

```python
def info_incr(self, key, inc=1)
```

增加监控信息中的数值。

<a name="info_add"></a>

### info\_add

```python
def info_add(self, key, count=1)
```

同 `info_incr`。

<a name="info_add_to_list"></a>

### info\_add\_to\_list

```python
def info_add_to_list(self, key, item)
```

将一个项添加到监控信息中的列表（如果键不存在则创建列表）。

<a name="info_clear"></a>

### info\_clear

```python
def info_clear(self)
```

清除当前任务的所有监控信息。

### 日志 (Logging)

<a name="log_info"></a>

### log\_info

```python
def log_info(self, message, notify=False)
```

记录一条信息级别的日志。

<a name="log_debug"></a>

### log\_debug

```python
def log_debug(self, message, notify=False)
```

记录一条调试级别的日志。

<a name="log_error"></a>

### log\_error

```python
def log_error(self, message, exception=None, notify=False)
```

记录一条错误级别的日志。

### 其他 (Other)

<a name="is_adb"></a>

### is\_adb

```python
def is_adb(self) -> bool
```

判断当前是否连接的是 ADB 设备（安卓/模拟器）。

<a name="is_browser"></a>

### is\_browser

```python
def is_browser(self) -> bool
```

判断当前是否正在控制浏览器设备。

<a name="adb_shell"></a>

### adb\_shell

```python
def adb_shell(self, *args, **kwargs) -> str
```

执行一条 ADB shell 指令并返回输出字符串。

<a name="ensure_in_front"></a>

### ensure\_in\_front

```python
def ensure_in_front(self)
```

确保游戏窗口或 ADB 模拟器处于前台显示状态。

<a name="box_of_screen"></a>

### box\_of\_screen

```python
def box_of_screen(self, x, y, to_x=1.0, to_y=1.0, width=0.0, height=0.0, name=None, hcenter=False, vcenter=False) -> Box
```

根据相对比例创建一个相对于当前屏幕尺寸的 `Box` 对象。

- **参数:**
    - `x`, `y` (float): 相对于屏幕的相对坐标 (0.0 - 1.0)。

<a name="box_of_screen_scaled"></a>

### box\_of\_screen\_scaled

```python
def box_of_screen_scaled(self, original_screen_width, original_screen_height, x_original, ...) -> Box
```

根据原始参考屏幕的分辨率，将坐标缩放到当前屏幕分辨率并创建一个 `Box`。

<a name="screen_width"></a>

### screen\_width

```python
@property
def screen_width(self) -> int
```

获取当前屏幕的像素宽度。

<a name="screen_height"></a>

### screen\_height

```python
@property
def screen_height(self) -> int
```

获取当前屏幕的像素高度。

<a name="width_of_screen"></a>

### width\_of\_screen

```python
def width_of_screen(self, percent) -> int
```

根据传入的百分比计算并返回对应的屏幕像素宽度。

<a name="wait_until"></a>

### wait\_until

```python
def wait_until(self, condition, time_out=0, pre_action=None, post_action=None, settle_time=-1, raise_if_not_found=False)
```

等待直到 `condition` 函数返回一个真值（或非空值）。

- **参数:**
    - `condition` (callable): 无参数的可调用函数。
    - `time_out` (int): 超时时间（秒），0 表示无限等待。

<a name="wait_scene"></a>

### wait\_scene

```python
def wait_scene(self, scene_type=None, time_out=0, pre_action=None, post_action=None)
```

等待当前场景变为指定的 `scene_type`。

<a name="sleep"></a>

### sleep

```python
def sleep(self, timeout)
```

让当前任务休眠指定秒数。休眠期间会处理脚本暂停和 `sleep_check`。

<a name="sleep_check"></a>

### sleep\_check

```python
def sleep_check(self)
```

当脚本休眠时，若设置了 `sleep_check_interval`，会定期调用此方法执行背景检查逻辑。

<a name="run_task_by_class"></a>

### run\_task\_by\_class

```python
def run_task_by_class(self, cls)
```

在当前任务上下文中实例化并运行指定的另一个任务类。

<a name="tr"></a>

### tr

```python
def tr(self, message) -> str
```

翻译指定的字符串消息（使用应用级的 i18n 系统）。

<a name="should_trigger"></a>

### should\_trigger

```python
def should_trigger(self) -> bool
```

根据配置的 `trigger_interval` 判断当前是否应该触发任务执行。

<a name="go_to_tab"></a>

### go\_to\_tab

```python
def go_to_tab(self, tab)
```

通知 UI 界面跳转到指定的选项卡。

<a name="find_boxes"></a>

### find\_boxes

```python
def find_boxes(self, boxes, match=None, boundary=None) -> list[Box]
```

对 `Box` 列表进行过滤，支持名称匹配和边界筛选。
