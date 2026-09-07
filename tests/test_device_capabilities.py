from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.device.DeviceManager import DeviceManager
from ok.device.capabilities import (
    DeviceCapabilities,
    MissingDeviceCapabilitiesError,
    NO_DEVICE_CAPABILITIES,
)
from ok.device.interaction_methods.base import BaseInteraction
from ok.task.task import BaseTask


def test_capabilities_default_to_fail_closed():
    assert DeviceCapabilities().enabled_names() == ()
    assert NO_DEVICE_CAPABILITIES.supports(DeviceCapabilities())
    assert not NO_DEVICE_CAPABILITIES.supports(
        DeviceCapabilities(keyboard_tap=True)
    )


def test_capabilities_report_only_required_missing_fields_in_stable_order():
    available = DeviceCapabilities(
        keyboard_tap=True,
        absolute_mouse=True,
        mouse_left=True,
        foreground_only=True,
    )
    required = DeviceCapabilities(
        keyboard_tap=True,
        keyboard_hold=True,
        absolute_mouse=True,
        mouse_left=True,
        mouse_middle=True,
        relative_mouse=True,
        foreground_only=True,
    )

    assert available.missing(required) == (
        "keyboard_hold",
        "mouse_middle",
        "relative_mouse",
    )
    assert not available.supports(required)


def test_relative_mouse_is_not_implicitly_required():
    available = DeviceCapabilities(
        keyboard_tap=True,
        keyboard_hold=True,
        absolute_mouse=True,
        mouse_left=True,
        mouse_right=True,
        mouse_middle=True,
        mouse_button_hold=True,
        foreground_only=True,
        relative_mouse=False,
    )
    locked_gameplay_requirement = DeviceCapabilities(
        keyboard_tap=True,
        keyboard_hold=True,
        mouse_left=True,
        mouse_middle=True,
        mouse_button_hold=True,
        foreground_only=True,
    )

    assert available.supports(locked_gameplay_requirement)


def test_from_names_and_overrides_reject_unknown_or_non_boolean_values():
    assert DeviceCapabilities.from_names(("keyboard_tap", "scroll")).enabled_names() == (
        "keyboard_tap",
        "scroll",
    )
    with pytest.raises(ValueError, match="unknown_capability"):
        DeviceCapabilities.from_names(("unknown_capability",))
    with pytest.raises(ValueError, match="unknown_capability"):
        DeviceCapabilities().with_overrides(unknown_capability=True)
    with pytest.raises(TypeError, match="bool"):
        DeviceCapabilities().with_overrides(keyboard_tap=1)


def test_base_interaction_and_unready_device_manager_expose_no_capabilities():
    interaction = BaseInteraction(capture=None)
    manager = DeviceManager.__new__(DeviceManager)
    manager.interaction = None

    assert interaction.get_capabilities() == NO_DEVICE_CAPABILITIES
    assert manager.capabilities == NO_DEVICE_CAPABILITIES

    manager.interaction = SimpleNamespace(
        get_capabilities=lambda: DeviceCapabilities(keyboard_tap=True)
    )
    assert manager.capabilities.keyboard_tap


def test_task_checks_requirements_before_enable():
    manager = SimpleNamespace(
        capabilities=DeviceCapabilities(keyboard_tap=True, foreground_only=True)
    )
    executor = SimpleNamespace(
        scene=None,
        device_manager=manager,
        exit_event=SimpleNamespace(),
    )
    app = SimpleNamespace(tr=lambda value: value)
    task = BaseTask(executor, app)
    task.required_capabilities = DeviceCapabilities(
        keyboard_tap=True,
        keyboard_hold=True,
        foreground_only=True,
    )

    assert task.missing_device_capabilities() == ("keyboard_hold",)
    assert task.get_device_compatibility_state() == {
        "status": "missing-capabilities",
        "level": None,
        "missing": ("keyboard_hold",),
        "reason": "",
    }
    assert not task.is_device_compatible()
    with pytest.raises(MissingDeviceCapabilitiesError) as exc_info:
        task.ensure_device_capabilities()

    assert exc_info.value.missing == ("keyboard_hold",)
    assert not task.enabled


def test_nested_task_execution_checks_capabilities_before_run():
    failure = MissingDeviceCapabilitiesError(("mouse_middle",), "Child")
    child = SimpleNamespace(
        info={"old": True},
        ensure_device_capabilities=Mock(side_effect=failure),
        run=Mock(),
    )
    parent = SimpleNamespace(
        info={"parent": True},
        get_task_by_class=Mock(return_value=child),
        log_error=Mock(),
    )

    with pytest.raises(MissingDeviceCapabilitiesError):
        BaseTask.run_task_by_class(parent, object)

    child.ensure_device_capabilities.assert_called_once_with()
    child.run.assert_not_called()
    assert child.info == {"old": True}
