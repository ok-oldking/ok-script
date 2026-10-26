import argparse
import importlib
import os
import sys


DEFAULT_CONFIG_TARGETS = ("src.config:config", "config:config")


def _split_target(target):
    if ":" in target:
        module_name, attr_name = target.split(":", 1)
    else:
        module_name, attr_name = target, "config"
    if not module_name or not attr_name:
        raise ValueError(f"Invalid config target: {target}")
    return module_name, attr_name


def load_config(target=None):
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    targets = (target,) if target else DEFAULT_CONFIG_TARGETS
    errors = []
    for item in targets:
        module_name, attr_name = _split_target(item)
        try:
            module = importlib.import_module(module_name)
            return getattr(module, attr_name)
        except Exception as e:
            errors.append(f"{item}: {e}")

    details = "\n".join(errors)
    raise RuntimeError(
        "Could not load config. Tried:\n"
        f"{details}\n"
        "Use --config module:attribute to point to your project config."
    )


def run_task_command(args):
    task = args.task_name or args.task
    if not task:
        raise ValueError("Task name is required. Use: ok run_task TaskName")

    from ok import run_task

    config = load_config(args.config)
    run_task(config, task=task, debug=args.debug, exit_after=args.exit_after)
    return 0


def run_gui_command(args):
    from ok import OK

    config = dict(load_config(args.config))
    config["gui"] = {"type": "qt"}
    if args.mcp:
        config["mcp"] = {**(config.get("mcp") or {}), "enabled": True}
        if args.mcp_port is not None:
            config["mcp"]["port"] = args.mcp_port
    OK(config).start()
    return 0


def run_mcp_command(args):
    from ok import OK

    config = dict(load_config(args.config))
    config['gui'] = None
    config['mcp'] = {**(config.get('mcp') or {}), 'enabled': True}
    if args.port is not None:
        config['mcp']['port'] = args.port
    runtime = OK(config)
    try:
        runtime.start_mcp_server()
        runtime.start()
    finally:
        runtime.quit()
        if runtime._mcp_server is not None:
            runtime._mcp_server.join()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="ok")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_task_parser = subparsers.add_parser("run_task", help="Run a task without starting the UI")
    run_task_parser.add_argument("task_name", nargs="?", help="Task name or class name to match")
    run_task_parser.add_argument("-t", "--task", help="Task name or class name to match")
    run_task_parser.add_argument("-d", "--debug", action="store_true", help="Run with debug mode enabled")
    run_task_parser.add_argument(
        "-e",
        "--exit",
        "--exit-after",
        "--exit_after",
        dest="exit_after",
        action="store_true",
        help="Exit the game and app after the task completes",
    )
    run_task_parser.add_argument(
        "-c",
        "--config",
        help="Config import target, for example src.config:config or config:config",
    )
    run_task_parser.set_defaults(func=run_task_command)

    gui_parser = subparsers.add_parser("gui", help="Run the Qt desktop UI")
    gui_parser.add_argument("-c", "--config", help="Config import target")
    gui_parser.add_argument("--mcp", action="store_true", help="Enable localhost MCP task development")
    gui_parser.add_argument("--mcp-port", type=int, help="Local MCP port (default: project config or 8765)")
    gui_parser.set_defaults(func=run_gui_command)

    mcp_parser = subparsers.add_parser("mcp", help="Serve task files over localhost MCP without the UI")
    mcp_parser.add_argument("-c", "--config", help="Config import target")
    mcp_parser.add_argument("--port", type=int, help="Local MCP port (default: project config or 8765)")
    mcp_parser.set_defaults(func=run_mcp_command)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        parser.exit(1, f"ok: error: {e}\n")


if __name__ == "__main__":
    raise SystemExit(main())
