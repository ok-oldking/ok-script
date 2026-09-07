"""平台中立的设备输入能力模型。

能力值描述当前已选择后端能够提供的行为契约，而不是代码是否存在。
例如 ``foreground_only=True`` 表示后端在每次普通输入前都会执行前台校验并
在失效时关闭输入闸门；仅仅能够发送系统全局事件不能满足该能力。
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Iterable


@dataclass(frozen=True)
class DeviceCapabilities:
    """可由任务查询的细粒度输入能力。

    所有字段默认关闭，避免新后端在尚未验证时因继承默认值而被误判为可用。
    ``relative_mouse`` 专指自由镜头所需的相对/delta 输入，不等同于把百分比坐标
    换算成绝对坐标的 ``move_relative`` 任务辅助函数。
    """

    keyboard_tap: bool = False
    keyboard_hold: bool = False
    absolute_mouse: bool = False
    mouse_left: bool = False
    mouse_right: bool = False
    mouse_middle: bool = False
    mouse_button_hold: bool = False
    scroll: bool = False
    relative_mouse: bool = False
    foreground_only: bool = False

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """按声明顺序返回全部能力名。"""
        return tuple(field.name for field in fields(cls))

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "DeviceCapabilities":
        """从能力名集合构造实例，并拒绝拼写错误。"""
        requested = tuple(names)
        unknown = sorted(set(requested) - set(cls.names()))
        if unknown:
            raise ValueError(f"Unknown device capabilities: {', '.join(unknown)}")
        return cls(**{name: True for name in requested})

    def enabled_names(self) -> tuple[str, ...]:
        """返回当前为真的能力名。"""
        return tuple(name for name in self.names() if getattr(self, name))

    def missing(self, required: "DeviceCapabilities") -> tuple[str, ...]:
        """返回本实例不能满足的必需能力。"""
        if not isinstance(required, DeviceCapabilities):
            raise TypeError("required must be a DeviceCapabilities instance")
        return tuple(
            name
            for name in self.names()
            if getattr(required, name) and not getattr(self, name)
        )

    def supports(self, required: "DeviceCapabilities") -> bool:
        """本实例是否满足 ``required`` 中全部为真的能力。"""
        return not self.missing(required)

    def with_overrides(self, **changes: bool) -> "DeviceCapabilities":
        """返回只修改指定能力的不可变副本。"""
        unknown = sorted(set(changes) - set(self.names()))
        if unknown:
            raise ValueError(f"Unknown device capabilities: {', '.join(unknown)}")
        if any(not isinstance(value, bool) for value in changes.values()):
            raise TypeError("device capability overrides must be bool values")
        return replace(self, **changes)


NO_DEVICE_CAPABILITIES = DeviceCapabilities()


class MissingDeviceCapabilitiesError(RuntimeError):
    """任务在执行前发现当前设备缺少必需能力。"""

    def __init__(self, missing: Iterable[str], task_name: str | None = None):
        self.missing = tuple(missing)
        self.task_name = task_name
        prefix = f"Task {task_name!r} " if task_name else "Task "
        detail = ", ".join(self.missing) if self.missing else "unknown"
        super().__init__(f"{prefix}requires unavailable device capabilities: {detail}")
