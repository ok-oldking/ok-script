import threading
from typing import Any, Callable, Dict, List, Optional, Union, Tuple
import numpy as np
import cv2
from qfluentwidgets import FluentIcon


class Box:
    """
    A class representing a bounding box with coordinates, dimensions, confidence, and name.

    表示边界框的类，包含坐标、尺寸、置信度和名称。
    """
    x: int
    y: int
    width: int
    height: int
    confidence: float
    name: Optional[Any]

    def __init__(self, x: Union[int, float], y: Union[int, float], width: Union[int, float] = 0,
                 height: Union[int, float] = 0, confidence: float = 1.0, name: Optional[Any] = None, to_x: int = -1,
                 to_y: int = -1) -> None:
        """
        Initializes a Box instance.

        初始化 Box 实例。

        :param x: The x-coordinate of the top-left corner. 左上角的 x 坐标。
        :param y: The y-coordinate of the top-left corner. 左上角的 y 坐标。
        :param width: The width of the box (alternative to to_x). 框的宽度（to_x 的替代）。
        :param height: The height of the box (alternative to to_y). 框的高度（to_y 的替代）。
        :param confidence: The confidence score of the detection. 检测的置信度分数。
        :param name: Optional name or label for the box. 可选的框名称或标签。
        :param to_x: The x-coordinate of the bottom-right corner (alternative to width). 右下角的 x 坐标（width 的替代）。
        :param to_y: The y-coordinate of the bottom-right corner (alternative to height). 右下角的 y 坐标（height 的替代）。
        """
        ...

    def __eq__(self, other: Any) -> bool:
        """
        Checks if two Box instances are equal.

        检查两个 Box 实例是否相等。

        :param other: The other Box instance to compare. 要比较的另一个 Box 实例。
        :return: True if equal, False otherwise. 如果相等返回 True，否则返回 False。
        """
        ...

    def area(self) -> int:
        """
        Calculates the area of the box.

        计算框的面积。

        :return: The area (width * height). 面积（宽度 * 高度）。
        """
        ...

    def in_boundary(self, boxes: List["Box"]) -> List["Box"]:
        """
        Finds boxes that are completely within this box's boundary.

        查找完全在此框边界内的框。

        :param boxes: List of boxes to check. 要检查的框列表。
        :return: List of boxes within the boundary. 在边界内的框列表。
        """
        ...

    def __repr__(self) -> str:
        """
        Returns a string representation of the Box for debugging.

        返回 Box 的字符串表示，用于调试。

        :return: String representation. 字符串表示。
        """
        ...

    def __str__(self) -> str:
        """
        Returns a detailed string representation of the Box.

        返回 Box 的详细字符串表示。

        :return: Detailed string. 详细字符串。
        """
        ...

    def scale(self, width_ratio: float, height_ratio: Optional[float] = None) -> "Box":
        """
        Scales the box by given ratios, keeping the center the same.

        通过给定比率缩放框，保持中心不变。

        :param width_ratio: Ratio to scale the width. 宽度缩放比率。
        :param height_ratio: Ratio to scale the height (defaults to width_ratio). 高度缩放比率（默认为宽度比率）。
        :return: New scaled Box. 新的缩放框。
        """
        ...

    def closest_distance(self, other: "Box") -> float:
        """
        Calculates the closest distance between two boxes.

        计算两个框之间的最近距离。

        :param other: The other Box. 另一个框。
        :return: The distance. 距离。
        """
        ...

    def center_distance(self, other: "Box") -> float:
        """
        Calculates the Euclidean distance between centers of two boxes.

        计算两个框中心之间的欧几里得距离。

        :param other: The other Box. 另一个框。
        :return: The distance. 距离。
        """
        ...

    def relative_with_variance(self, relative_x: float = 0.5, relative_y: float = 0.5) -> tuple[int, int]:
        """
        Gets a point relative to the box with random variance.

        获取相对于框的点，带有随机方差。

        :param relative_x: Relative x position (0-1). 相对 x 位置（0-1）。
        :param relative_y: Relative y position (0-1). 相对 y 位置（0-1）。
        :return: (x, y) coordinates. (x, y) 坐标。
        """
        ...

    def copy(self, x_offset: int = 0, y_offset: int = 0, width_offset: int = 0, height_offset: int = 0,
             name: Optional[Any] = None) -> "Box":
        """
        Creates a copy of the box with offsets.

        创建框的副本，带有偏移。

        :param x_offset: Offset for x. x 偏移。
        :param y_offset: Offset for y. y 偏移。
        :param width_offset: Offset for width. 宽度偏移。
        :param height_offset: Offset for height. 高度偏移。
        :param name: New name (defaults to original). 新名称（默认为原名称）。
        :return: New Box. 新框。
        """
        ...

    def crop_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Crops the frame to this box's area.

        将帧裁剪到此框的区域。

        :param frame: The image frame. 图像帧。
        :return: Cropped frame. 裁剪后的帧。
        """
        ...

    def center(self) -> tuple[float, float]:
        """
        Gets the center coordinates of the box.

        获取框的中心坐标。

        :return: (x, y) center. (x, y) 中心。
        """
        ...

    def find_closest_box(self, direction: str, boxes: List["Box"],
                         condition: Optional[Callable[["Box"], bool]] = None) -> Optional["Box"]:
        """
        Finds the closest box in a given direction.

        在给定方向查找最近的框。

        :param direction: Direction ('up', 'down', 'left', 'right', 'all'). 方向（'up', 'down', 'left', 'right', 'all'）。
        :param boxes: List of boxes to search. 要搜索的框列表。
        :param condition: Optional condition function. 可选条件函数。
        :return: Closest Box or None. 最近的框或 None。
        """
        ...

class ExecutorOperation:
    """
    Base class for operations in the task executor.

    任务执行器中操作的基类。
    """
    last_click_time: float
    _executor: "TaskExecutor"

    def __init__(self, executor: "TaskExecutor") -> None:
        """
        Initializes the ExecutorOperation.

        初始化 ExecutorOperation。

        :param executor: The task executor instance. 任务执行器实例。
        """
        ...

    def exit_is_set(self) -> bool:
        """
        Checks if the exit event is set.

        检查退出事件是否设置。

        :return: True if set, False otherwise. 如果设置返回 True，否则 False。
        """
        ...

    def get_task_by_class(self, cls: type) -> Optional["BaseTask"]:
        """
        Gets a task by its class.

        通过类获取任务。

        :param cls: The task class. 任务类。
        :return: The task instance or None. 任务实例或 None。
        """
        ...

    def box_in_horizontal_center(self, box: Optional["Box"], off_percent: float = 0.02) -> bool:
        """
        Checks if a box is in the horizontal center.

        检查框是否在水平中心。

        :param box: The box to check. 要检查的框。
        :param off_percent: Offset percentage tolerance. 偏移百分比容差。
        :return: True if centered, False otherwise. 如果居中返回 True，否则 False。
        """
        ...

    def clipboard(self) -> str:
        """
        Gets the clipboard content.

        获取剪贴板内容。

        :return: Clipboard text. 剪贴板文本。
        """
        ...

    def is_scene(self, the_scene: type) -> bool:
        """
        Checks if the current scene matches the given type.

        检查当前场景是否匹配给定类型。

        :param the_scene: The scene class. 场景类。
        :return: True if matches, False otherwise. 如果匹配返回 True，否则 False。
        """
        ...

    def reset_scene(self) -> None:
        """
        Resets the current scene.

        重置当前场景。
        """
        ...

    def click(self, x: Union[int, "Box", List["Box"]] = -1, y: int = -1, move_back: bool = False,
              name: Optional[str] = None, interval: int = -1, move: bool = True, down_time: float = 0.01,
              after_sleep: float = 0, key: str = 'left') -> bool:
        """
        Performs a click action.

        执行点击动作。

        :param x: X coordinate or Box/List[Box]. x 坐标或 Box/List[Box]。
        :param y: Y coordinate. y 坐标。
        :param move_back: Move back after click. 点击后移回。
        :param name: Name for logging. 日志名称。
        :param interval: Click interval check. 点击间隔检查。
        :param move: Move mouse before click. 点击前移动鼠标。
        :param down_time: Mouse down time. 鼠标按下时间。
        :param after_sleep: Sleep after click. 点击后睡眠。
        :param key: Mouse button ('left', 'middle', 'right'). 鼠标按钮（'left', 'middle', 'right'）。
        :return: True if successful. 如果成功返回 True。
        """
        ...

    def back(self, after_sleep: float = 0) -> None:
        """
        Sends a back key event.

        发送返回键事件。

        :param after_sleep: Sleep after back. 返回后睡眠。
        """
        ...

    def middle_click(self, x: Union[int, "Box", List["Box"]] = -1, y: int = -1, move_back: bool = False,
                     down_time: float = 0.01) -> bool:
        """
        Performs a middle click.

        执行中键点击。

        :param x: X coordinate or Box/List[Box]. x 坐标或 Box/List[Box]。
        :param y: Y coordinate. y 坐标。
        :param move_back: Move back after click. 点击后移回。
        :param down_time: Mouse down time. 鼠标按下时间。
        :return: True if successful. 如果成功返回 True。
        """
        ...

    def right_click(self, x: Union[int, "Box", List["Box"]] = -1, y: int = -1, move_back: bool = False,
                    down_time: float = 0.01) -> bool:
        """
        Performs a right click.

        执行右键点击。

        :param x: X coordinate or Box/List[Box]. x 坐标或 Box/List[Box]。
        :param y: Y coordinate. y 坐标。
        :param move_back: Move back after click. 点击后移回。
        :param down_time: Mouse down time. 鼠标按下时间。
        :return: True if successful. 如果成功返回 True。
        """
        ...

    def mouse_down(self, x: int = -1, y: int = -1, name: Optional[str] = None, key: str = "left") -> None:
        """
        Presses the mouse button down.

        按下鼠标按钮。

        :param x: X coordinate. x 坐标。
        :param y: Y coordinate. y 坐标。
        :param name: Name for logging. 日志名称。
        :param key: Mouse button. 鼠标按钮。
        """
        ...

    def mouse_up(self, name: Optional[str] = None, key: str = "left") -> None:
        """
        Releases the mouse button.

        释放鼠标按钮。

        :param name: Name for logging. 日志名称。
        :param key: Mouse button. 鼠标按钮。
        """
        ...

    def swipe_relative(self, from_x: float, from_y: float, to_x: float, to_y: float, duration: float = 0.5,
                       settle_time: float = 0) -> None:
        """
        Performs a relative swipe.

        执行相对滑动。

        :param from_x: Start relative X. 起始相对 X。
        :param from_y: Start relative Y. 起始相对 Y。
        :param to_x: End relative X. 结束相对 X。
        :param to_y: End relative Y. 结束相对 Y。
        :param duration: Duration in seconds. 持续时间（秒）。
        :param settle_time: Settle time after swipe. 滑动后稳定时间。
        """
        ...

    def input_text(self, text: str) -> None:
        """
        Inputs text.

        输入文本。

        :param text: Text to input. 要输入的文本。
        """
        ...

    def ensure_in_front(self) -> None:
        """
        Ensures the window is in front.

        确保窗口在前台。
        """
        ...

    def scroll_relative(self, x: float, y: float, count: int) -> None:
        """
        Performs relative scroll.

        执行相对滚动。

        :param x: Relative X. 相对 X。
        :param y: Relative Y. 相对 Y。
        :param count: Scroll count. 滚动计数。
        """
        ...

    def scroll(self, x: int, y: int, count: int) -> None:
        """
        Performs scroll at position.

        在位置执行滚动。

        :param x: X coordinate. x 坐标。
        :param y: Y coordinate. y 坐标。
        :param count: Scroll count. 滚动计数。
        """
        ...

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5, after_sleep: float = 0.1,
              settle_time: float = 0) -> None:
        """
        Performs swipe gesture.

        执行滑动手势。

        :param from_x: Start X. 起始 X。
        :param from_y: Start Y. 起始 Y。
        :param to_x: End X. 结束 X。
        :param to_y: End Y. 结束 Y。
        :param duration: Duration. 持续时间。
        :param after_sleep: Sleep after. 后睡眠。
        :param settle_time: Settle time. 稳定时间。
        """
        ...

    def screenshot(self, name: Optional[str] = None, frame: Optional[np.ndarray] = None, show_box: bool = False,
                   frame_box: Optional["Box"] = None) -> None:
        """
        Takes a screenshot.

        拍摄截图。

        :param name: Screenshot name. 截图名称。
        :param frame: Frame to save. 要保存的帧。
        :param show_box: Show box. 显示框。
        :param frame_box: Frame box. 帧框。
        """
        ...

    def click_box(self, box: Union["Box", List["Box"], str] = None, relative_x: float = 0.5, relative_y: float = 0.5,
                  raise_if_not_found: bool = False, move_back: bool = False, down_time: float = 0.01,
                  after_sleep: float = 1) -> bool:
        """
        Clicks on a box.

        点击框。

        :param box: Box or name. 框或名称。
        :param relative_x: Relative X in box. 框内相对 X。
        :param relative_y: Relative Y in box. 框内相对 Y。
        :param raise_if_not_found: Raise if not found. 未找到时抛出异常。
        :param move_back: Move back after. 点击后移回。
        :param down_time: Down time. 按下时间。
        :param after_sleep: Sleep after. 后睡眠。
        :return: True if clicked. 如果点击返回 True。
        """
        ...

    def wait_scene(self, scene_type: Optional[type] = None, time_out: float = 0, pre_action: Optional[Callable] = None,
                   post_action: Optional[Callable] = None) -> Any:
        """
        Waits for a scene.

        等待场景。

        :param scene_type: Scene type. 场景类型。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :return: Result. 结果。
        """
        ...

    def sleep(self, timeout: float) -> bool:
        """
        Sleeps for a duration.

        睡眠一段时间。

        :param timeout: Sleep time. 睡眠时间。
        :return: Always True. 总是 True。
        """
        ...

    def send_key(self, key: Union[str, int], down_time: float = 0.02, interval: int = -1,
                 after_sleep: float = 0) -> bool:
        """
        Sends a key event.

        发送键事件。

        :param key: Key to send. 要发送的键。
        :param down_time: Down time. 按下时间。
        :param interval: Interval check. 间隔检查。
        :param after_sleep: Sleep after. 后睡眠。
        :return: True if sent. 如果发送返回 True。
        """
        ...

    def get_global_config(self, option: "ConfigOption") -> Config:
        """
        Gets global config.

        获取全局配置。

        :param option: Config option. 配置选项。
        :return: Config. 配置。
        """
        ...

    def get_global_config_desc(self, option: "ConfigOption") -> Dict[str, str]:
        """
        Gets global config descriptions.

        获取全局配置描述。

        :param option: Config option. 配置选项。
        :return: Descriptions. 描述。
        """
        ...

    def send_key_down(self, key: Union[str, int]) -> None:
        """
        Sends key down.

        发送键按下。

        :param key: Key. 键。
        """
        ...

    def send_key_up(self, key: Union[str, int]) -> None:
        """
        Sends key up.

        发送键抬起。

        :param key: Key. 键。
        """
        ...

    def wait_until(self, condition: Callable[[], Any], time_out: float = 0, pre_action: Optional[Callable] = None,
                   post_action: Optional[Callable] = None, settle_time: float = -1,
                   raise_if_not_found: bool = False) -> Any:
        """
        Waits until condition is true.

        等待直到条件为真。

        :param condition: Condition function. 条件函数。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :param settle_time: Settle time. 稳定时间。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :return: Result. 结果。
        """
        ...

    def wait_click_box(self, condition: Callable[[], List["Box"]], time_out: float = 0,
                       pre_action: Optional[Callable] = None, post_action: Optional[Callable] = None,
                       raise_if_not_found: bool = False) -> List["Box"]:
        """
        Waits and clicks on box.

        等待并点击框。

        :param condition: Condition. 条件。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :return: Boxes. 框。
        """
        ...

    def next_frame(self) -> np.ndarray:
        """
        Gets next frame.

        获取下一帧。

        :return: Frame. 帧。
        """
        ...

    def adb_ui_dump(self) -> Optional[str]:
        """
        Dumps ADB UI.

        转储 ADB UI。

        :return: XML content or None. XML 内容或 None。
        """
        ...

    @property
    def frame(self) -> np.ndarray:
        """
        Gets current frame.

        获取当前帧。

        :return: Frame. 帧。
        """
        ...

    @staticmethod
    def draw_boxes(feature_name: Optional[str] = None, boxes: Optional[List["Box"]] = None, color: str = "red",
                   debug: bool = True) -> None:
        """
        Draws boxes.

        绘制框。

        :param feature_name: Feature name. 特征名称。
        :param boxes: Boxes to draw. 要绘制的框。
        :param color: Color. 颜色。
        :param debug: Debug mode. 调试模式。
        """
        ...

    def clear_box(self) -> None:
        """
        Clears boxes.

        清除框。
        """
        ...

    def calculate_color_percentage(self, color: Dict[str, tuple[int, int]], box: Union["Box", str]) -> float:
        """
        Calculates color percentage in box.

        计算框中颜色百分比。

        :param color: Color range. 颜色范围。
        :param box: Box or name. 框或名称。
        :return: Percentage. 百分比。
        """
        ...

    def adb_shell(self, *args: Any, **kwargs: Any) -> Optional[str]:
        """
        Executes ADB shell command.

        执行 ADB shell 命令。

        :param args: Arguments. 参数。
        :param kwargs: Keyword arguments. 关键字参数。
        :return: Output or None. 输出或 None。
        """
        ...

class FindFeature(ExecutorOperation):
    """
    Class for finding features in images.

    在图像中查找特征的类。
    """

    def __init__(self, executor: "TaskExecutor") -> None:
        """
        Initializes FindFeature.

        初始化 FindFeature。

        :param executor: Executor. 执行器。
        """
        ...

    def find_feature(self, feature_name: Optional[str] = None, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x: int = -1,
                     y: int = -1, to_x: int = -1, to_y: int = -1, width: int = -1, height: int = -1,
                     box: Optional[Union["Box", str]] = None, canny_lower: int = 0, canny_higher: int = 0,
                     frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                     template: Optional[np.ndarray] = None, match_method: int = cv2.TM_CCOEFF_NORMED,
                     screenshot: bool = False, mask_function: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                     frame: Optional[np.ndarray] = None) -> List["Box"]:
        """
        Finds features in frame.

        在帧中查找特征。

        :param feature_name: Feature name. 特征名称。
        :param horizontal_variance: Horizontal variance. 水平方差。
        :param vertical_variance: Vertical variance. 垂直方差。
        :param threshold: Threshold. 阈值。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param x: X start. X 开始。
        :param y: Y start. Y 开始。
        :param to_x: X end. X 结束。
        :param to_y: Y end. Y 结束。
        :param width: Width. 宽度。
        :param height: Height. 高度。
        :param box: Box. 框。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param frame_processor: Frame processor. 帧处理器。
        :param template: Template. 模板。
        :param match_method: Match method. 匹配方法。
        :param screenshot: Screenshot. 截图。
        :param mask_function: Mask function. 掩码函数。
        :param frame: Frame. 帧。
        :return: Boxes. 框列表。
        """
        ...

    def get_feature_by_name(self, name: str) -> Optional["Feature"]:
        """
        Gets feature by name.

        通过名称获取特征。

        :param name: Name. 名称。
        :return: Feature or None. 特征或 None。
        """
        ...

    def get_box_by_name(self, name: str) -> Optional["Box"]:
        """
        Gets box by name.

        通过名称获取框。

        :param name: Name. 名称。
        :return: Box or None. 框或 None。
        """
        ...

    def find_feature_and_set(self, features: Union[str, List[str]], horizontal_variance: float = 0,
                             vertical_variance: float = 0, threshold: float = 0) -> bool:
        """
        Finds and sets features.

        查找并设置特征。

        :param features: Features. 特征。
        :param horizontal_variance: Horizontal variance. 水平方差。
        :param vertical_variance: Vertical variance. 垂直方差。
        :param threshold: Threshold. 阈值。
        :return: True if all found. 如果全部找到返回 True。
        """
        ...

    def wait_feature(self, feature: str, horizontal_variance: float = 0, vertical_variance: float = 0,
                     threshold: float = 0, time_out: float = 0, pre_action: Optional[Callable] = None,
                     post_action: Optional[Callable] = None, use_gray_scale: bool = False, box: Optional["Box"] = None,
                     raise_if_not_found: bool = False, canny_lower: int = 0, canny_higher: int = 0,
                     settle_time: float = -1, frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None) -> \
    Optional["Box"]:
        """
        Waits for feature.

        等待特征。

        :param feature: Feature. 特征。
        :param horizontal_variance: Horizontal variance. 水平方差。
        :param vertical_variance: Vertical variance. 垂直方差。
        :param threshold: Threshold. 阈值。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param box: Box. 框。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param settle_time: Settle time. 稳定时间。
        :param frame_processor: Frame processor. 帧处理器。
        :return: Box or None. 框或 None。
        """
        ...

    def wait_click_feature(self, feature: str, horizontal_variance: float = 0, vertical_variance: float = 0,
                           threshold: float = 0, relative_x: float = 0.5, relative_y: float = 0.5, time_out: float = 0,
                           pre_action: Optional[Callable] = None, post_action: Optional[Callable] = None,
                           box: Optional["Box"] = None, raise_if_not_found: bool = True, use_gray_scale: bool = False,
                           canny_lower: int = 0, canny_higher: int = 0, click_after_delay: float = 0,
                           settle_time: float = -1, after_sleep: float = 0) -> bool:
        """
        Waits and clicks feature.

        等待并点击特征。

        :param feature: Feature. 特征。
        :param horizontal_variance: Horizontal variance. 水平方差。
        :param vertical_variance: Vertical variance. 垂直方差。
        :param threshold: Threshold. 阈值。
        :param relative_x: Relative X. 相对 X。
        :param relative_y: Relative Y. 相对 Y。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :param box: Box. 框。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param click_after_delay: Delay after click. 点击后延迟。
        :param settle_time: Settle time. 稳定时间。
        :param after_sleep: Sleep after. 后睡眠。
        :return: True if clicked. 如果点击返回 True。
        """
        ...

    def find_one(self, feature_name: Optional[str] = None, horizontal_variance: float = 0, vertical_variance: float = 0,
                 threshold: float = 0, use_gray_scale: bool = False, box: Optional["Box"] = None, canny_lower: int = 0,
                 canny_higher: int = 0, frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                 template: Optional[np.ndarray] = None,
                 mask_function: Optional[Callable[[np.ndarray], np.ndarray]] = None, frame: Optional[np.ndarray] = None,
                 match_method: int = cv2.TM_CCOEFF_NORMED, screenshot: bool = False) -> Optional["Box"]:
        """
        Finds one feature.

        查找一个特征。

        :param feature_name: Feature name. 特征名称。
        :param horizontal_variance: Horizontal variance. 水平方差。
        :param vertical_variance: Vertical variance. 垂直方差。
        :param threshold: Threshold. 阈值。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param box: Box. 框。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param frame_processor: Frame processor. 帧处理器。
        :param template: Template. 模板。
        :param mask_function: Mask function. 掩码函数。
        :param frame: Frame. 帧。
        :param match_method: Match method. 匹配方法。
        :param screenshot: Screenshot. 截图。
        :return: Box or None. 框或 None。
        """
        ...

    def on_feature(self, boxes: List["Box"]) -> None:
        """
        Callback on feature found.

        找到特征的回调。

        :param boxes: Boxes. 框。
        """
        ...

    def feature_exists(self, feature_name: str) -> bool:
        """
        Checks if feature exists.

        检查特征是否存在。

        :param feature_name: Feature name. 特征名称。
        :return: True if exists. 如果存在返回 True。
        """
        ...

    def find_best_match_in_box(self, box: "Box", to_find: List[str], threshold: float, use_gray_scale: bool = False,
                               canny_lower: int = 0, canny_higher: int = 0,
                               frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                               mask_function: Optional[Callable[[np.ndarray], np.ndarray]] = None) -> Optional["Box"]:
        """
        Finds best match in box.

        在框中查找最佳匹配。

        :param box: Box. 框。
        :param to_find: To find. 要查找。
        :param threshold: Threshold. 阈值。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param frame_processor: Frame processor. 帧处理器。
        :param mask_function: Mask function. 掩码函数。
        :return: Best box or None. 最佳框或 None。
        """
        ...

    def find_first_match_in_box(self, box: "Box", to_find: List[str], threshold: float, use_gray_scale: bool = False,
                                canny_lower: int = 0, canny_higher: int = 0,
                                frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                                mask_function: Optional[Callable[[np.ndarray], np.ndarray]] = None) -> Optional["Box"]:
        """
        Finds first match in box.

        在框中查找第一个匹配。

        :param box: Box. 框。
        :param to_find: To find. 要查找。
        :param threshold: Threshold. 阈值。
        :param use_gray_scale: Use grayscale. 使用灰度。
        :param canny_lower: Canny lower. Canny 下限。
        :param canny_higher: Canny higher. Canny 上限。
        :param frame_processor: Frame processor. 帧处理器。
        :param mask_function: Mask function. 掩码函数。
        :return: First box or None. 第一个框或 None。
        """
        ...

class OCR(FindFeature):
    """
    Optical Character Recognition class.

    光学字符识别类。
    """
    ocr_default_threshold: float

    def __init__(self, executor: "TaskExecutor") -> None:
        """
        Initializes OCR.

        初始化 OCR。

        :param executor: Executor. 执行器。
        """
        ...

    def ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1,
            match: Optional[Union[str, List[str], "re.Pattern", List["re.Pattern"]]] = None, width: int = 0,
            height: int = 0, box: Optional[Union["Box", str]] = None, name: Optional[str] = None, threshold: float = 0,
            frame: Optional[np.ndarray] = None, target_height: int = 0, use_grayscale: bool = False, log: bool = False,
            frame_processor: Optional[Callable[[np.ndarray], np.ndarray]] = None, lib: str = 'default') -> List["Box"]:
        """
        Performs OCR on region.

        在区域执行 OCR。

        :param x: Relative X start. 相对 X 开始。
        :param y: Relative Y start. 相对 Y 开始。
        :param to_x: Relative X end. 相对 X 结束。
        :param to_y: Relative Y end. 相对 Y 结束。
        :param match: Match pattern. 匹配模式。
        :param width: Width. 宽度。
        :param height: Height. 高度。
        :param box: Box. 框。
        :param name: Name. 名称。
        :param threshold: Threshold. 阈值。
        :param frame: Frame. 帧。
        :param target_height: Target height. 目标高度。
        :param use_grayscale: Use grayscale. 使用灰度。
        :param log: Log results. 日志结果。
        :param frame_processor: Frame processor. 帧处理器。
        :param lib: OCR library. OCR 库。
        :return: Boxes. 框列表。
        """
        ...

    def wait_click_ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1, width: int = 0,
                       height: int = 0, box: Optional["Box"] = None, name: Optional[str] = None,
                       match: Optional[Any] = None, threshold: float = 0, frame: Optional[np.ndarray] = None,
                       target_height: int = 0, time_out: int = 0, raise_if_not_found: bool = False,
                       recheck_time: float = 0, after_sleep: float = 0, post_action: Optional[Callable] = None,
                       log: bool = False, settle_time: float = -1, lib: str = "default") -> Optional[List["Box"]]:
        """
        Waits and clicks OCR result.

        等待并点击 OCR 结果。

        :param x: X start. X 开始。
        :param y: Y start. Y 开始。
        :param to_x: X end. X 结束。
        :param to_y: Y end. Y 结束。
        :param width: Width. 宽度。
        :param height: Height. 高度。
        :param box: Box. 框。
        :param name: Name. 名称。
        :param match: Match. 匹配。
        :param threshold: Threshold. 阈值。
        :param frame: Frame. 帧。
        :param target_height: Target height. 目标高度。
        :param time_out: Timeout. 超时。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :param recheck_time: Recheck time. 重新检查时间。
        :param after_sleep: Sleep after. 后睡眠。
        :param post_action: Post action. 后动作。
        :param log: Log. 日志。
        :param settle_time: Settle time. 稳定时间。
        :param lib: Library. 库。
        :return: Boxes or None. 框或 None。
        """
        ...

    def wait_ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1, width: int = 0, height: int = 0,
                 name: Optional[str] = None, box: Optional["Box"] = None, match: Optional[Any] = None,
                 threshold: float = 0, frame: Optional[np.ndarray] = None, target_height: int = 0, time_out: int = 0,
                 post_action: Optional[Callable] = None, raise_if_not_found: bool = False, log: bool = False,
                 settle_time: float = -1, lib: str = "default") -> Optional[List["Box"]]:
        """
        Waits for OCR result.

        等待 OCR 结果。

        :param x: X start. X 开始。
        :param y: Y start. Y 开始。
        :param to_x: X end. X 结束。
        :param to_y: Y end. Y 结束。
        :param width: Width. 宽度。
        :param height: Height. 高度。
        :param name: Name. 名称。
        :param box: Box. 框。
        :param match: Match. 匹配。
        :param threshold: Threshold. 阈值。
        :param frame: Frame. 帧。
        :param target_height: Target height. 目标高度。
        :param time_out: Timeout. 超时。
        :param post_action: Post action. 后动作。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :param log: Log. 日志。
        :param settle_time: Settle time. 稳定时间。
        :param lib: Library. 库。
        :return: Boxes or None. 框或 None。
        """
        ...

class BaseTask(OCR):
    """
    Base class for tasks.

    任务的基类。
    """
    name: str
    description: str
    _enabled: bool
    config: Config
    info: Dict[str, Any]
    default_config: Dict[str, Any]
    config_description: Dict[str, str]
    config_type: Dict[str, Any]
    _paused: bool
    lock: threading.Lock
    _handler: Optional["Handler"]
    running: bool
    exit_after_task: bool
    trigger_interval: int
    last_trigger_time: float
    start_time: float
    icon: Optional[Any]
    supported_languages: List[str]
    group_name: str
    group_icon: FluentIcon

    def __init__(self, executor: Optional["TaskExecutor"] = None) -> None:
        """
        Initializes BaseTask.

        初始化 BaseTask。

        :param executor: Executor. 执行器。
        """
        ...

    def run_task_by_class(self, cls: type["BaseTask"]) -> None:
        """
        Runs task by class.

        通过类运行任务。

        :param cls: Task class. 任务类。
        """
        ...

    def tr(self, message: str) -> str:
        """
        Translates message.

        翻译消息。

        :param message: Message. 消息。
        :return: Translated message. 翻译后的消息。
        """
        ...

    def should_trigger(self) -> bool:
        """
        Checks if should trigger.

        检查是否应触发。

        :return: True if should. 如果应返回 True。
        """
        ...

    def is_custom(self) -> bool:
        """
        Checks if custom task.

        检查是否自定义任务。

        :return: True if custom. 如果自定义返回 True。
        """
        ...

    def add_first_run_alert(self, first_run_alert: str) -> None:
        """
        Adds first run alert.

        添加首次运行警报。

        :param first_run_alert: Alert message. 警报消息。
        """
        ...

    def add_exit_after_config(self) -> None:
        """
        Adds exit after config.

        添加退出后配置。
        """
        ...

    def get_status(self) -> str:
        """
        Gets task status.

        获取任务状态。

        :return: Status string. 状态字符串。
        """
        ...

    def enable(self) -> None:
        """
        Enables task.

        启用任务。
        """
        ...

    def pause(self) -> None:
        """
        Pauses task.

        暂停任务。
        """
        ...

    def unpause(self) -> None:
        """
        Unpauses task.

        取消暂停任务。
        """
        ...

    @property
    def paused(self) -> bool:
        """
        Checks if paused.

        检查是否暂停。

        :return: True if paused. 如果暂停返回 True。
        """
        ...

    def log_info(self, message: str, notify: bool = False) -> None:
        """
        Logs info.

        日志信息。

        :param message: Message. 消息。
        :param notify: Notify. 通知。
        """
        ...

    def log_debug(self, message: str, notify: bool = False) -> None:
        """
        Logs debug.

        日志调试。

        :param message: Message. 消息。
        :param notify: Notify. 通知。
        """
        ...

    def log_error(self, message: str, exception: Optional[Exception] = None, notify: bool = False) -> None:
        """
        Logs error.

        日志错误。

        :param message: Message. 消息。
        :param exception: Exception. 异常。
        :param notify: Notify. 通知。
        """
        ...

    def go_to_tab(self, tab: str) -> None:
        """
        Goes to tab.

        转到标签。

        :param tab: Tab name. 标签名称。
        """
        ...

    def notification(self, message: str, title: Optional[str] = None, error: bool = False, tray: bool = False,
                     show_tab: Optional[str] = None) -> None:
        """
        Shows notification.

        显示通知。

        :param message: Message. 消息。
        :param title: Title. 标题。
        :param error: Error flag. 错误标志。
        :param tray: Tray. 托盘。
        :param show_tab: Show tab. 显示标签。
        """
        ...

    @property
    def enabled(self) -> bool:
        """
        Checks if enabled.

        检查是否启用。

        :return: True if enabled. 如果启用返回 True。
        """
        ...

    def info_clear(self) -> None:
        """
        Clears info.

        清除信息。
        """
        ...

    def info_incr(self, key: str, inc: int = 1) -> None:
        """
        Increments info value.

        递增信息值。

        :param key: Key. 键。
        :param inc: Increment. 增量。
        """
        ...

    def info_add_to_list(self, key: str, item: Union[Any, List[Any]]) -> None:
        """
        Adds to info list.

        添加到信息列表。

        :param key: Key. 键。
        :param item: Item. 项目。
        """
        ...

    def info_set(self, key: str, value: Any) -> None:
        """
        Sets info value.

        设置信息值。

        :param key: Key. 键。
        :param value: Value. 值。
        """
        ...

    def info_get(self, *args: Any, **kwargs: Any) -> Any:
        """
        Gets info value.

        获取信息值。

        :param args: Args. 参数。
        :param kwargs: Kwargs. 关键字参数。
        :return: Value. 值。
        """
        ...

    def info_add(self, key: str, count: int = 1) -> None:
        """
        Adds to info.

        添加到信息。

        :param key: Key. 键。
        :param count: Count. 计数。
        """
        ...

    def load_config(self) -> None:
        """
        Loads config.

        加载配置。
        """
        ...

    def validate_config(self, key: str, value: Any) -> Optional[str]:
        """
        Validates config.

        验证配置。

        :param key: Key. 键。
        :param value: Value. 值。
        :return: Message or None. 消息或 None。
        """
        ...

    def disable(self) -> None:
        """
        Disables task.

        禁用任务。
        """
        ...

    @property
    def hwnd_title(self) -> str:
        """
        Gets HWND title.

        获取 HWND 标题。

        :return: Title. 标题。
        """
        ...

    def run(self) -> None:
        """
        Runs the task.

        运行任务。
        """
        ...

    def trigger(self) -> bool:
        """
        Triggers the task.

        触发任务。

        :return: True if triggered. 如果触发返回 True。
        """
        ...

    def on_destroy(self) -> None:
        """
        On destroy callback.

        销毁回调。
        """
        ...

    def on_create(self) -> None:
        """
        On create callback.

        创建回调。
        """
        ...

    def set_executor(self, executor: "TaskExecutor") -> None:
        """
        Sets executor.

        设置执行器。

        :param executor: Executor. 执行器。
        """
        ...

    def find_boxes(self, boxes: List["Box"], match: Optional[Any] = None,
                   boundary: Optional[Union["Box", str]] = None) -> List["Box"]:
        """
        Finds boxes with match and boundary.

        使用匹配和边界查找框。

        :param boxes: Boxes. 框。
        :param match: Match. 匹配。
        :param boundary: Boundary. 边界。
        :return: Filtered boxes. 过滤后的框。
        """
        ...

class TriggerTask(BaseTask):
    """
    Trigger task class.

    触发任务类。
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initializes TriggerTask.

        初始化 TriggerTask。
        """
        ...

    def on_create(self) -> None:
        """
        On create.

        创建时。
        """
        ...

    def get_status(self) -> str:
        """
        Gets status.

        获取状态。

        :return: Status. 状态。
        """
        ...

    def enable(self) -> None:
        """
        Enables.

        启用。
        """
        ...

    def disable(self) -> None:
        """
        Disables.

        禁用。
        """
        ...

class TaskExecutor:
    """
    Task executor class.

    任务执行器类。
    """
    _frame: Optional[np.ndarray]
    paused: bool
    pause_start: float
    pause_end_time: float
    _last_frame_time: float
    wait_until_timeout: float
    device_manager: "DeviceManager"
    feature_set: Optional["FeatureSet"]
    wait_until_settle_time: float
    wait_scene_timeout: float
    exit_event: threading.Event
    debug_mode: bool
    debug: bool
    global_config: "GlobalConfig"
    _ocr_lib: Dict[str, Any]
    ocr_target_height: int
    current_task: Optional["BaseTask"]
    config_folder: str
    trigger_task_index: int
    trigger_tasks: List["TriggerTask"]
    onetime_tasks: List["BaseTask"]
    thread: Optional[threading.Thread]
    locale: "QLocale"
    scene: Optional["BaseScene"]
    text_fix: Dict[str, str]
    ocr_po_translation: Any
    config: Dict[str, Any]
    basic_options: Config
    lock: threading.Lock

    def __init__(self, device_manager: "DeviceManager", wait_until_timeout: float = 10,
                 wait_until_settle_time: float = -1, exit_event: Optional[threading.Event] = None,
                 feature_set: Optional["FeatureSet"] = None, ocr_lib: Optional[Dict[str, Any]] = None,
                 config_folder: Optional[str] = None, debug: bool = False,
                 global_config: Optional["GlobalConfig"] = None, ocr_target_height: int = 0,
                 config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initializes TaskExecutor.

        初始化 TaskExecutor。

        :param device_manager: Device manager. 设备管理器。
        :param wait_until_timeout: Wait timeout. 等待超时。
        :param wait_until_settle_time: Settle time. 稳定时间。
        :param exit_event: Exit event. 退出事件。
        :param feature_set: Feature set. 特征集。
        :param ocr_lib: OCR lib. OCR 库。
        :param config_folder: Config folder. 配置文件夹。
        :param debug: Debug mode. 调试模式。
        :param global_config: Global config. 全局配置。
        :param ocr_target_height: OCR target height. OCR 目标高度。
        :param config: Config. 配置。
        """
        ...

    @property
    def interaction(self) -> "BaseInteraction":
        """
        Gets interaction.

        获取交互。

        :return: Interaction. 交互。
        """
        ...

    @property
    def method(self) -> "BaseCaptureMethod":
        """
        Gets method.

        获取方法。

        :return: Method. 方法。
        """
        ...

    def ocr_lib(self, name: str = "default") -> Any:
        """
        Gets OCR lib.

        获取 OCR 库。

        :param name: Name. 名称。
        :return: Lib. 库。
        """
        ...

    def nullable_frame(self) -> Optional[np.ndarray]:
        """
        Gets nullable frame.

        获取可为空帧。

        :return: Frame or None. 帧或 None。
        """
        ...

    def check_frame_and_resolution(self, supported_ratio: Optional[str], min_size: Optional[tuple[int, int]],
                                   time_out: float = 8.0) -> tuple[bool, str]:
        """
        Checks frame and resolution.

        检查帧和分辨率。

        :param supported_ratio: Supported ratio. 支持比率。
        :param min_size: Min size. 最小尺寸。
        :param time_out: Timeout. 超时。
        :return: (Valid, Resolution str). (有效, 分辨率字符串)。
        """
        ...

    def can_capture(self) -> bool:
        """
        Checks if can capture.

        检查是否可以捕获。

        :return: True if can. 如果可以返回 True。
        """
        ...

    def next_frame(self) -> np.ndarray:
        """
        Gets next frame.

        获取下一帧。

        :return: Frame. 帧。
        """
        ...

    def is_executor_thread(self) -> bool:
        """
        Checks if executor thread.

        检查是否执行器线程。

        :return: True if is. 如果是返回 True。
        """
        ...

    def connected(self) -> bool:
        """
        Checks if connected.

        检查是否连接。

        :return: True if connected. 如果连接返回 True。
        """
        ...

    @property
    def frame(self) -> np.ndarray:
        """
        Gets frame.

        获取帧。

        :return: Frame. 帧。
        """
        ...

    def sleep(self, timeout: float) -> None:
        """
        Sleeps.

        睡眠。

        :param timeout: Timeout. 超时。
        """
        ...

    def pause(self, task: Optional["BaseTask"] = None) -> bool:
        """
        Pauses.

        暂停。

        :param task: Task. 任务。
        :return: True if paused. 如果暂停返回 True。
        """
        ...

    def stop_current_task(self) -> None:
        """
        Stops current task.

        停止当前任务。
        """
        ...

    def start(self) -> None:
        """
        Starts.

        开始。
        """
        ...

    def wait_condition(self, condition: Callable[[], Any], time_out: float = 0, pre_action: Optional[Callable] = None,
                       post_action: Optional[Callable] = None, settle_time: float = -1,
                       raise_if_not_found: bool = False) -> Any:
        """
        Waits condition.

        等待条件。

        :param condition: Condition. 条件。
        :param time_out: Timeout. 超时。
        :param pre_action: Pre action. 前动作。
        :param post_action: Post action. 后动作。
        :param settle_time: Settle time. 稳定时间。
        :param raise_if_not_found: Raise if not found. 未找到抛出异常。
        :return: Result. 结果。
        """
        ...

    def reset_scene(self, check_enabled: bool = True) -> None:
        """
        Resets scene.

        重置场景。

        :param check_enabled: Check enabled. 检查启用。
        """
        ...

    def active_trigger_task_count(self) -> int:
        """
        Gets active trigger count.

        获取活跃触发计数。

        :return: Count. 计数。
        """
        ...

    def execute(self) -> None:
        """
        Executes tasks.

        执行任务。
        """
        ...

    def stop(self) -> None:
        """
        Stops.

        停止。
        """
        ...

    def wait_until_done(self) -> None:
        """
        Waits until done.

        等待直到完成。
        """
        ...

    def get_all_tasks(self) -> List["BaseTask"]:
        """
        Gets all tasks.

        获取所有任务。

        :return: Tasks. 任务列表。
        """
        ...

    def get_task_by_class_name(self, class_name: str) -> Optional["BaseTask"]:
        """
        Gets task by class name.

        通过类名获取任务。

        :param class_name: Class name. 类名。
        :return: Task or None. 任务或 None。
        """
        ...

    def get_task_by_class(self, cls: type["BaseTask"]) -> Optional["BaseTask"]:
        """
        Gets task by class.

        通过类获取任务。

        :param cls: Class. 类。
        :return: Task or None. 任务或 None。
        """
        ...


class OkGlobals:
    # Instance attributes initialized in __init__
    app: Any
    executor: Any
    device_manager: Any
    handler: Any
    auth_uid: Optional[str]
    auth_rd: Optional[str]
    auth_expire: int
    trial_expire: int
    my_app: Any
    dpi_scaling: float
    ok: Any
    config: Any
    task_manager: Any
    app_path: str
    use_dml: bool
    global_config: Any

    def __init__(self) -> None: ...

    def set_use_dml(self) -> None:
        """
        Sets self.use_dml based on global_config 'Basic Options'.

        Logic:
        1. Checks 'Use DirectML' config option ('Auto' or 'Yes').
        2. If 'Auto': checks if NV free GPU memory > 3000 MiB.
        3. Validates if Windows build number >= 18362.
        """
        ...

    def get_trial_expire_util_str(self) -> str:
        """
        Converts self.trial_expire timestamp to a formatted string: '%Y-%m-%d %H:%M:%S'.
        """
        ...

    def get_expire_util_str(self) -> str:
        """
        Converts self.auth_expire timestamp to a formatted string: '%Y-%m-%d %H:%M:%S'.
        """
        ...

    def set_dpi_scaling(self, window: Any) -> None:
        """
        Sets self.dpi_scaling based on the screen associated with the provided window handle.

        Args:
            window: A UI window object (likely PySide/PyQt) containing a windowHandle().
        """
        ...


og: OkGlobals


class Config(Dict[str, Any]):
    """
    A dictionary-like object for managing configuration that persists to a JSON file.
    """

    # Class attribute specifying the default folder for config files.
    config_folder: str

    # --- Instance Attributes ---
    default: Dict[str, Any]
    validator: Optional[Callable[[str, Any], Tuple[bool, str]]]
    config_file: str

    def __init__(self, name: str, default: Dict[str, Any], folder: Optional[str] = ...,
                 validator: Optional[Callable[[str, Any], Tuple[bool, str]]] = ...) -> None:
        """
        Initialize the Config object.

        Loads configuration from a JSON file. If the file doesn't exist or is invalid,
        it falls back to the provided default configuration and creates the file.

        Args:
            name: Name of the config file (without .json extension).
            default: A dictionary containing default configuration values.
            folder: Optional folder where the config file is stored.
            validator: Optional function to validate key-value pairs during setup and modification.
                       The function should accept (key, value) and return (is_valid, message).
        """
        ...

    def save_file(self) -> None:
        """
        Save the current configuration state to its associated JSON file.
        This is called automatically on most modifications.
        """
        ...

    def get_default(self, key: str) -> Any:
        """
        Get a value from the original default configuration dictionary.

        Args:
            key: The key to look up in the default config.
        """
        ...

    def reset_to_default(self) -> None:
        """
        Reset the entire configuration to the default values and save the file.
        """
        ...

    # --- Overridden dict methods that trigger a file save ---

    def pop(self, key: str, default: Any = ...) -> Any:
        """
        Remove and return a value from the configuration, then save the file.

        Args:
            key: The key to remove.
            default: The value to return if the key does not exist.
        """
        ...

    def popitem(self) -> Tuple[str, Any]:
        """
        Remove and return the last key-value pair, then save the file.
        """
        ...

    def clear(self) -> None:
        """
        Clear all items from the configuration and save the empty state to the file.
        """
        ...

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Set a configuration value. If the value is different from the existing one
        and passes validation, the change is saved to the file.
        """
        ...

    # --- Other methods ---

    def __getitem__(self, key: str) -> Any:
        """
        Retrieve a configuration value by its key.
        """
        ...

    def has_user_config(self) -> bool:
        """
        Check if the configuration contains any user-defined keys (i.e., keys that
        do not start with an underscore).
        """
        ...

    def validate(self, key: str, value: Any) -> bool:
        """
        Validate a key-value pair using the configured validator function.

        Args:
            key: The key to validate.
            value: The value to validate.

        Returns:
            True if the pair is valid or if no validator is set, False otherwise.
        """
        ...

    def verify_config(self, current: Dict[str, Any], default_config: Dict[str, Any]) -> bool:
        """
        Verify the loaded configuration against the default configuration.
        - Removes keys from 'current' that are not in 'default_config'.
        - Adds missing keys from 'default_config' to 'current'.
        - Ensures values have the correct type, falling back to default if not.
        - Validates existing values, falling back to default if invalid.

        Args:
            current: The configuration dictionary loaded from the file.
            default_config: The default configuration to compare against.

        Returns:
            True if the configuration was modified during verification, False otherwise.
        """
        ...

class Logger:
    """
    A Cython wrapper class for logging messages.
    It prefixes messages with the logger's name.
    """

    # --- C-level attributes (exposed to Python) ---
    logger: Any  # The underlying Python logger object (e.g., from logging module).
    name: str  # The short name of the logger, derived from the full name.

    def __init__(self, name: str) -> None:
        """
        Initializes the Logger with a given name.

        Args:
            name: The full name for the logger (e.g., 'module.submodule.class').
                  The short name will be extracted from this.
        """
        ...

    # --- Logging methods ---

    def debug(self, message: Any) -> None:
        """Logs a message with the DEBUG level."""
        ...

    def info(self, message: Any) -> None:
        """Logs a message with the INFO level."""
        ...

    def warning(self, message: Any) -> None:
        """Logs a message with the WARNING level."""
        ...

    def error(self, message: Any, exception: Optional[Exception] = ...) -> None:
        """
        Logs a message with the ERROR level.
        If an exception is provided, its traceback is appended to the message.

        Args:
            message: The error message to log.
            exception: An optional Exception object to format and include.
        """
        ...

    def critical(self, message: Any) -> None:
        """Logs a message with the CRITICAL level."""
        ...

    # --- Static methods ---

    @staticmethod
    def call_stack() -> str:
        """Returns a formatted string of the current call stack."""
        ...

    @staticmethod
    def get_logger(name: str) -> 'Logger':
        """
        Factory method to create a new Logger instance.

        Args:
            name: The name for the new logger.

        Returns:
            A new instance of the Logger class.
        """
        ...

    @staticmethod
    def exception_to_str(exception: Exception) -> str:
        """
        Converts an exception object into a formatted traceback string.

        Args:
            exception: The exception to format.

        Returns:
            A string containing the formatted traceback.
        """
        ...