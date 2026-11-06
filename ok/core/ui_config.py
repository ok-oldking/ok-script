from pathlib import Path


# Fits a 1600x900 screen with a taskbar (about 1600x852 available). The minimum
# equals the default so the layout always looks the same.
DEFAULT_WINDOW_SIZE = {
    "width": 1560,
    "height": 820,
    "min_width": 1560,
    "min_height": 820,
}

GUI_TYPES = {"qt"}


def resolve_gui_icon(config):
    """Keep custom icons, otherwise use the PNG shipped with the package."""
    return config.get("gui_icon") or str(Path(__file__).resolve().parents[1] / "assets/default-icon.png")


def resolve_ui_config(config):
    """Resolve the nested UI schema, with legacy top-level compatibility."""
    if "gui" in config:
        raw_gui = config.get("gui")
        if raw_gui is None:
            return None
        if not isinstance(raw_gui, dict):
            raise ValueError("gui must be a mapping")
        gui_type = raw_gui.get("type")
        if gui_type not in GUI_TYPES:
            raise ValueError("gui.type must be 'qt'")
        window_size = raw_gui.get("window_size") or config.get("window_size")
    elif config.get("use_gui"):
        gui_type = "qt"
        window_size = config.get("window_size")
    else:
        return None

    return {
        "type": gui_type,
        "window_size": dict(window_size or DEFAULT_WINDOW_SIZE),
    }


def resolve_window_size(config):
    ui_config = resolve_ui_config(config)
    if ui_config is not None:
        return ui_config["window_size"]
    return dict(config.get("window_size") or DEFAULT_WINDOW_SIZE)
