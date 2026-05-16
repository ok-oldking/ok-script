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
    run_task(config, task=task, debug=args.debug)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="ok")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_task_parser = subparsers.add_parser("run_task", help="Run a task without starting the UI")
    run_task_parser.add_argument("task_name", nargs="?", help="Task name or class name to match")
    run_task_parser.add_argument("-t", "--task", help="Task name or class name to match")
    run_task_parser.add_argument("-d", "--debug", action="store_true", help="Run with debug mode enabled")
    run_task_parser.add_argument(
        "-c",
        "--config",
        help="Config import target, for example src.config:config or config:config",
    )
    run_task_parser.set_defaults(func=run_task_command)

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
