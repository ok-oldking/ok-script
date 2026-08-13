DEFAULT_WINDOW_SIZE = {
    "width": 1200,
    "height": 800,
    "min_width": 1200,
    "min_height": 800,
}

GUI_TYPES = {"qt", "web"}
WEB_LAUNCH_MODES = {"pywebview", "browser", "server"}


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
            raise ValueError("gui.type must be 'qt' or 'web'")
        launch_mode = raw_gui.get("launch_mode", "pywebview")
        if gui_type == "web" and launch_mode not in WEB_LAUNCH_MODES:
            raise ValueError(
                "gui.launch_mode must be 'pywebview', 'browser', or 'server'"
            )
        window_size = raw_gui.get("window_size") or config.get("window_size")
    elif config.get("use_gui"):
        gui_type = "qt"
        launch_mode = None
        window_size = config.get("window_size")
    else:
        return None

    resolved = {
        "type": gui_type,
        "window_size": dict(window_size or DEFAULT_WINDOW_SIZE),
    }
    if gui_type == "web":
        resolved["launch_mode"] = launch_mode
    return resolved


def resolve_window_size(config):
    ui_config = resolve_ui_config(config)
    if ui_config is not None:
        return ui_config["window_size"]
    return dict(config.get("window_size") or DEFAULT_WINDOW_SIZE)
