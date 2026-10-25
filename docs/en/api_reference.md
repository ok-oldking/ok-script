# API reference

[Documentation](index.md) · [Quick start](quick_start.md) · [Advanced guide](advanced.md) · [简体中文](../api_doc/README.md)

This is a practical reference for task authors. The implementation is available in [`ok/task/task.py`](https://github.com/ok-oldking/ok-script/blob/master/ok/task/task.py) and [`ok/feature/Box.py`](https://github.com/ok-oldking/ok-script/blob/master/ok/feature/Box.py). Optional parameters are omitted from some summaries; inspect the linked source or your IDE signature help for the complete signature.

## Importing task APIs

A typical application task inherits from `BaseTask`:

```python
from ok import BaseTask


class ClaimRewardTask(BaseTask):
    def run(self):
        reward = self.wait_feature("reward_button", time_out=5)
        if reward:
            self.click_box(reward)
```

Recognition methods generally return a `Box`, a list of boxes, or `None`/an empty list when no match is found.

## `Box`

`Box` represents a rectangular screen region.

```python
from ok import Box

box = Box(x=100, y=200, width=80, height=40, name="confirm")
```

Important attributes include `x`, `y`, `width`, `height`, `confidence`, and `name`.

| Method | Purpose |
| --- | --- |
| `Box(x, y, width=0, height=0, confidence=1.0, name=None, to_x=-1, to_y=-1)` | Create a box from a position and size, or from opposite corners. |
| `area()` | Return `width × height`. |
| `center()` | Return the center coordinates. |
| `scale(width_ratio, height_ratio=None)` | Return a scaled box. |
| `copy(...)` | Copy the box with optional position and size offsets. |
| `crop_frame(frame)` | Crop this region from an image frame. |
| `in_boundary(boxes)` | Test whether the box lies within supplied boundaries. |
| `center_distance(other)` | Calculate distance between box centers. |
| `closest_distance(other)` | Calculate the shortest edge-to-edge distance. |
| `relative_with_variance(relative_x=0.5, relative_y=0.5)` | Convert a relative position inside the box to screen coordinates with variance. |
| `find_closest_box(direction, boxes, condition=None)` | Find the nearest box in a direction. |

## Frames and screenshots

| API | Purpose |
| --- | --- |
| `frame()` | Return the current cached frame. |
| `next_frame()` | Request and return a fresh frame. |
| `screenshot(name=None, frame=None, show_box=False, frame_box=None)` | Save a screenshot for debugging or test data. |
| `screen_width()` / `screen_height()` | Return the active capture dimensions. |
| `width_of_screen(percent)` | Convert a screen-width ratio to pixels. |
| `box_of_screen(...)` | Build a `Box` from relative screen coordinates. |
| `box_of_screen_scaled(...)` | Convert coordinates from a reference resolution to the current screen. |

Use relative screen coordinates where possible so a task can adapt to different resolutions.

## Mouse, keyboard, and touch input

| API | Purpose |
| --- | --- |
| `click(x, y, ...)` | Click coordinates, a `Box`, or a list of boxes. |
| `click_box(box, relative_x=0.5, relative_y=0.5, ...)` | Click a relative position inside a box. |
| `click_box_if_name_match(boxes, names, ...)` | Click boxes whose recognized names match. |
| `click_relative(x, y, ...)` | Click at screen-relative coordinates. |
| `wait_click_box(condition, time_out=0, ...)` | Wait for a callable to return a box, then click it. |
| `right_click(...)` / `middle_click(...)` | Send alternate mouse-button clicks. |
| `move(x, y)` / `move_relative(x, y)` | Move the pointer without clicking. |
| `mouse_down(...)` / `mouse_up(...)` | Control mouse-button state directly. |
| `scroll(x, y, count)` | Scroll at absolute coordinates. |
| `scroll_relative(x, y, count)` | Scroll at relative coordinates. |
| `swipe(from_x, from_y, to_x, to_y, duration=0.5, ...)` | Swipe between absolute coordinates. |
| `swipe_relative(...)` | Swipe between relative coordinates. |
| `input_text(text)` | Enter text through the active interaction backend. |
| `send_key(key, down_time=0.02, ...)` | Press and release a key. |
| `send_key_down(key)` / `send_key_up(key)` | Control key state directly. |
| `back(...)` | Send the platform-appropriate back action. |

Input methods normally include timing and post-action delay parameters. Use those delays instead of raw `time.sleep()` so task cancellation remains responsive.

## Template matching

| API | Return value and purpose |
| --- | --- |
| `find_feature(feature_name, ...)` | Return all matches for one or more named COCO features. |
| `find_one(feature_name, ...)` | Return the best single match. |
| `wait_feature(feature, time_out=0, ...)` | Poll until a feature appears or timeout expires. |
| `wait_click_feature(feature, ...)` | Wait for a feature and click it. |
| `feature_exists(feature_name)` | Return whether a named feature is available in the asset set. |
| `get_feature_by_name(name)` | Return the stored feature definition. |
| `get_box_by_name(name)` | Return the annotated reference box. |
| `find_feature_and_set(features, ...)` | Match several features and return the matching set. |
| `find_best_match_in_box(box, to_find, threshold, ...)` | Match a supplied image inside a box and return the best result. |
| `find_first_match_in_box(box, to_find, threshold, ...)` | Return the first acceptable image match inside a box. |

Frequently used matching options include:

- `threshold`: minimum similarity;
- `horizontal_variance` and `vertical_variance`: expand the expected search region;
- `use_gray_scale`: ignore color where supported;
- `frame`: reuse a known frame to keep several recognition calls consistent.

```python
confirm = self.find_one("confirm_button", threshold=0.8)
if confirm:
    self.click_box(confirm)
```

## OCR

| API | Purpose |
| --- | --- |
| `ocr(...)` | Recognize text in a relative region or `Box`. |
| `wait_ocr(..., time_out=0, ...)` | Poll until matching text is recognized. |
| `wait_click_ocr(...)` | Wait for recognized text and click its box. |
| `add_text_fix(fix)` | Add an OCR correction rule for common recognition errors. |

`match` accepts the text-matching expression used by the configured OCR engine. Restrict OCR to the smallest stable region that contains the target text; this improves both speed and accuracy.

```python
result = self.wait_ocr(box=self.box_of_screen(0.6, 0.7, 0.95, 0.95),
                       match="Confirm|OK", time_out=5)
```

## Color analysis

`calculate_color_percentage(color, box)` returns the proportion of a region that matches a color definition. `box` may be a `Box` or a named feature region.

```python
health_ratio = self.calculate_color_percentage("#34c759", "health_bar")
```

## Waiting and task flow

| API | Purpose |
| --- | --- |
| `wait_until(condition, time_out=0, ...)` | Poll a callable until it returns a truthy result. |
| `wait_scene(scene_type=None, time_out=0, ...)` | Wait for a scene transition. |
| `sleep(timeout)` | Cancellation-aware task sleep. |
| `sleep_check()` | Hook called during managed sleeps. |
| `run_task_by_class(cls)` | Run another registered task class while sharing task info. |
| `should_trigger()` | Enforce `trigger_interval` for trigger tasks. |

Callbacks such as `pre_action` and `post_action` can perform work before or after polling. Set `raise_if_not_found=True` where absence is an actual task error rather than a normal branch.

## Device helpers

| API | Purpose |
| --- | --- |
| `is_adb()` | Return whether the active target uses ADB or an emulator device. |
| `is_browser()` | Return whether the active interaction is browser-based. |
| `adb_ui_dump()` | Retrieve the current Android UI hierarchy. |
| `adb_shell(*args, **kwargs)` | Execute an ADB shell command through the device manager. |
| `ensure_in_front()` | Bring or keep the target in an interactable state. |

Check `is_adb()` before calling device-specific operations in tasks that support both Windows and Android.

## Configuration

Configure task controls in the task constructor:

```python
class ExampleTask(BaseTask):
    def __init__(self):
        super().__init__()
        self.default_config = {
            "Enabled": True,
            "Attempts": 3,
            "Mode": "Normal",
        }
        self.config_description = {
            "Attempts": "Maximum number of attempts",
        }
        self.config_type = {
            "Mode": {"type": "drop_down", "options": ["Normal", "Safe"]},
        }
```

| API or attribute | Purpose |
| --- | --- |
| `default_config` | Default values shown in the task UI. |
| `config_description` | Human-readable help for configuration keys. |
| `config_type` | UI editor definitions for non-default input types. |
| `load_config()` | Load persisted task configuration. |
| `validate_config(key, value)` | Validate or normalize a changed value. |
| `get_global_config(option)` | Read a global application option. |
| `get_global_config_desc(option)` | Read a global option description. |

## Task status and messages

| API | Purpose |
| --- | --- |
| `info_set(key, value)` / `info_get(...)` | Store or retrieve values displayed for the running task. |
| `info_incr(key, inc=1)` | Increment a numeric task value. |
| `info_add(key, count=1)` | Add to a task counter. |
| `info_add_to_list(key, item)` | Append one or more items to a task list. |
| `info_clear()` | Clear all task information. |
| `log_info(message, notify=False, images=None, screenshot=False)` | Log an informational message; optional OpenCV frames are saved asynchronously. |
| `log_debug(message, notify=False, images=None, screenshot=False)` | Log a debug message; optional OpenCV frames are saved asynchronously. |
| `log_error(message, exception=None, notify=False, images=None, screenshot=False)` | Log an error and always save the current frame. |
| `notification(message, title=None, ..., images=None, screenshot=False)` | Show an application notification, save optional frames, and dispatch enabled providers. |
| `tr(message)` | Translate a task string through the application translator. |
| `go_to_tab(tab)` | Navigate the application UI to a tab. |

## Debug overlays

| API | Purpose |
| --- | --- |
| `draw_boxes(feature_name=None, boxes=None, color="red", debug=True)` | Draw recognition boxes on the debug overlay. |
| `clear_box()` | Clear overlay boxes. |
| `get_overlay_view()` | Return the active overlay view. |

Overlays should be treated as debug output; production task logic must rely on recognition results, not overlay state.

## Finding related boxes

`find_boxes(boxes, match=None, boundary=None)` filters or relates recognized boxes by text/name and boundary. `Box.find_closest_box()` is useful for directional UI navigation when several candidates are present.

## Testing

Use `TaskTestCase` to run task methods against fixed screenshots:

```python
from ok.test.TaskTestCase import TaskTestCase


class TestClaimReward(TaskTestCase):
    task_class = ClaimRewardTask

    def test_reward_button(self):
        self.set_image("tests/images/reward_screen.png")
        self.assertIsNotNone(self.task.find_one("reward_button"))
```

See the [advanced guide](advanced.md#3-automated-task-tests) for the complete testing workflow.
