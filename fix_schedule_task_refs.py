"""
一次性校正计划任务索引的工具 (fix_schedule_task_refs)

背景
----
ok-script 的 Windows 计划任务通过 `-t N`（1-based 索引）定位 onetime_tasks。
当 config.py 中 onetime_tasks 顺序被重排后，已创建的计划任务仍指向旧索引。

本工具复用 schedule_index_sync.sync_schedule_task_indexes()，
与启动时自动校正逻辑为单一实现；通常在 GUI 无法正常启动时手动运行。

用法（在应用根目录运行）
------------------------
    python fix_schedule_task_refs.py
    python fix_schedule_task_refs.py --config src.config:config

它会：
1. 加载应用配置，实例化 onetime_tasks（读取每个任务的 name）；
2. 读取 configs/schedule_tasks_cache.json；
3. 只处理本应用（如 \\ok-ef\\）下的任务；
4. 用 name 在当前 onetime_tasks 中查新索引，把 `-t X`（旧索引或历史任务名）
   改写为新索引，并同步更新缓存 / Windows 计划任务（COM）。
"""

import argparse
import sys

from ok.cli import load_config
from ok.util.clazz import init_class_by_name


class _ExecutorStub:
    """仅用于实例化任务以读取 name 的最小 executor 桩。

    ExecutorOperation.__init__ 只访问 executor.scene，因此足够。
    """

    def __init__(self):
        self.scene = None
        self.onetime_tasks = []
        self.trigger_tasks = []


class _AppStub:
    """任务实例化所需的最小 app 桩。"""

    debug = False
    headless = True
    po_translation = "Failed"

    def tr(self, key):
        return key


def build_onetime_tasks(config) -> list:
    """从配置的 onetime_tasks 列表实例化任务（顺序即当前索引顺序）。"""
    tasks = []
    executor = _ExecutorStub()
    app = _AppStub()
    for task_class in config.get("onetime_tasks", []):
        try:
            task = init_class_by_name(task_class[0], task_class[1], executor=executor, app=app)
            # after_init/post_init 只用于读取 name，失败不阻塞（name 在 __init__ 已就绪）
            try:
                task.after_init(executor=executor, scene=executor.scene)
                task.post_init()
            except Exception:
                pass
            tasks.append(task)
            print(f"  loaded task #{len(tasks)}: {getattr(task, 'name', '?')}")
        except Exception as e:
            print(f"  skipped task {task_class}: {e}")
    return tasks


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fix schedule task -t indexes after onetime_tasks reorder"
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Config import target, e.g. src.config:config or config:config",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    tasks = build_onetime_tasks(config)
    if not tasks:
        print("No onetime_tasks loaded, nothing to correct.")
        return 1

    from ok.ui.qt.tasks.schedule_index_sync import sync_schedule_task_indexes

    corrected = sync_schedule_task_indexes(onetime_tasks=tasks)
    print(f"Corrected {corrected} schedule task(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
