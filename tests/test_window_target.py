from dataclasses import FrozenInstanceError, replace

import pytest

from ok.device.window_target import (
    BaseDesktopWindowTarget,
    StableWindowHint,
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowMatchHints,
    WindowRefreshStatus,
    WindowSelectionStatus,
    select_window_candidate,
)
from ok.device.window_target.windows import WindowsHwndWindowTarget


def candidate(
        *,
        pid=10,
        window_id=20,
        bundle_id="com.example.game",
        app_name="Example Game",
        title="Example Game",
        layer=0,
        geometry=None,
        frontmost=False):
    return WindowCandidate(
        process_id=pid,
        window_id=window_id,
        bundle_identifier=bundle_id,
        application_name=app_name,
        title=title,
        layer=layer,
        outer_geometry=geometry or WindowGeometry(10, 20, 1280, 720),
        frontmost=frontmost,
    )


def test_window_value_objects_are_immutable_and_validate_geometry():
    item = candidate()

    with pytest.raises(FrozenInstanceError):
        item.window_id = 21
    with pytest.raises(ValueError, match="non-negative"):
        WindowGeometry(0, 0, -1, 10)
    with pytest.raises(ValueError, match="finite and positive"):
        replace(candidate(), display_scale=float("nan"))
    with pytest.raises(ValueError, match="dimensions must be finite"):
        WindowMatchHints(minimum_width=float("nan"))


def test_stable_hint_round_trip_excludes_volatile_runtime_identity():
    hint = candidate().stable_hint()

    assert hint.to_mapping() == {
        "bundle_identifier": "com.example.game",
        "application_name": "Example Game",
        "title": "Example Game",
    }
    assert StableWindowHint.from_mapping(hint.to_mapping()) == hint
    with pytest.raises(ValueError, match="volatile fields: process_id, window_id"):
        StableWindowHint.from_mapping({
            "process_id": 10,
            "window_id": 20,
        })


def test_lost_target_clears_runtime_identity_and_geometry():
    target = BaseDesktopWindowTarget(candidate())

    target._update_candidate(None, exists=False)

    assert not target.snapshot.exists
    assert target.snapshot.candidate is None
    assert target.process_id == 0
    assert target.window_id == 0
    assert target.outer_geometry is None
    assert target.generation == 2


def test_title_only_hint_requires_manual_selection_even_for_one_candidate():
    result = select_window_candidate(
        [candidate(bundle_id=None, app_name="Unknown")],
        WindowMatchHints(title_patterns=("Example",)),
    )

    assert result.status is WindowSelectionStatus.MANUAL_SELECTION_REQUIRED
    assert result.selected is None
    assert [item.window_id for item in result.candidates] == [20]


def test_title_only_persisted_hint_still_requires_manual_selection():
    result = select_window_candidate(
        [candidate(bundle_id=None, app_name="")],
        WindowMatchHints(title_patterns=("Example",)),
        stable_hint=StableWindowHint(title="Example Game"),
    )

    assert result.status is WindowSelectionStatus.MANUAL_SELECTION_REQUIRED
    assert result.selected is None


def test_unique_application_identity_can_select_but_multiple_windows_cannot():
    hints = WindowMatchHints(application_names=("Example Game",))

    selected = select_window_candidate([candidate()], hints)
    ambiguous = select_window_candidate(
        [candidate(window_id=20), candidate(window_id=21)], hints)

    assert selected.status is WindowSelectionStatus.SELECTED
    assert selected.selected.window_id == 20
    assert ambiguous.status is WindowSelectionStatus.MANUAL_SELECTION_REQUIRED
    assert ambiguous.selected is None


def test_unique_identity_match_ignores_unrelated_eligible_windows():
    result = select_window_candidate(
        [
            candidate(),
            candidate(
                pid=30,
                window_id=40,
                bundle_id='com.example.other',
                app_name='Other App',
                title='Other'),
        ],
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )

    assert result.status is WindowSelectionStatus.SELECTED
    assert result.selected.window_id == 20


def test_stable_application_identity_survives_a_changed_window_title():
    result = select_window_candidate(
        [candidate(app_name='Renamed Game', title='Game - New Session')],
        WindowMatchHints(),
        stable_hint=StableWindowHint(
            bundle_identifier='com.example.game',
            application_name='Example Game',
            title='Example Game',
        ),
    )

    assert result.status is WindowSelectionStatus.SELECTED
    assert result.selected.application_name == 'Renamed Game'
    assert result.selected.title == 'Game - New Session'


def test_manual_selection_can_choose_eligible_fallback_without_persisting_ids():
    result = select_window_candidate(
        [candidate(pid=30, window_id=40, bundle_id=None, app_name="Manual App")],
        WindowMatchHints(title_patterns=("Does not match",)),
        manual_window_id=40,
    )

    assert result.status is WindowSelectionStatus.SELECTED
    assert result.selected.runtime_identity == (30, 40)
    assert result.stable_hint.to_mapping() == {
        "application_name": "Manual App",
        "title": "Example Game",
    }


class FakeHwndWindow:
    hwnd = 100
    exists = True
    x = 10
    y = 20
    window_width = 1300
    window_height = 760
    width = 1280
    height = 720
    real_width = 1280
    real_height = 720
    scaling = 1.25
    exe_full_path = r"C:\Games\ExampleGame.exe"
    hwnd_title = "Example Game"

    def __init__(self):
        self.foreground = False
        self.activation_requests = 0
        self.refreshes = 0

    def get_capture_origin(self):
        return 20, 50

    def is_foreground(self):
        return self.foreground

    def bring_to_front(self):
        self.activation_requests += 1
        return True

    def do_update_window_size(self):
        self.refreshes += 1


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


def test_windows_adapter_wraps_hwnd_without_changing_activation_semantics():
    hwnd = FakeHwndWindow()
    clock = FakeClock()
    target = WindowsHwndWindowTarget(
        hwnd,
        process_id_resolver=lambda _hwnd: 77,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert target.process_id == 77
    assert target.window_id == 100
    assert target.application_name == "ExampleGame.exe"
    assert target.outer_geometry == WindowGeometry(
        10, 20, 1300, 760,
        WindowCoordinateSpace.WINDOWS_LEGACY_DESKTOP)
    assert target.capture_geometry == WindowGeometry(
        20, 50, 1280, 720,
        WindowCoordinateSpace.WINDOWS_LEGACY_CAPTURE)
    assert target.generation == 1

    assert target.request_activation()
    assert hwnd.activation_requests == 1
    assert not target.wait_for_observed_activation(0.1, poll_interval=0.05)

    hwnd.foreground = True
    assert target.wait_for_observed_activation(0)
    assert target.refresh().status is WindowRefreshStatus.UNCHANGED

    hwnd.width = 1600
    assert target.refresh().status is WindowRefreshStatus.UPDATED
    assert target.generation == 2

    hwnd.hwnd = 101
    assert target.refresh().status is WindowRefreshStatus.REBOUND
    assert target.generation == 3
