import ast
import glob
import hashlib
import os.path

from ok.task.task import BaseTask, TriggerTask
from ok.util.clazz import init_class_by_name
from ok.util.logger import Logger

import sys
import importlib.util
from ok import og

logger = Logger.get_logger(__name__)


class TaskManager:
    def __init__(self, task_executor, app, trigger_tasks=[], onetime_tasks=[], scene=None):
        self.task_executor = task_executor
        self.app = app
        self.custom_tasks_enabled = og.config.get('custom_tasks', False)
        if self.custom_tasks_enabled:
            self.task_folder = os.path.join(os.getcwd(), 'ok_tasks')
            if not os.path.exists(self.task_folder):
                os.makedirs(self.task_folder)
        else:
            self.task_folder = os.path.join("user_scripts", "tasks")
        self.has_custom = self.custom_tasks_enabled or os.path.exists(self.task_folder)
        self.task_map = dict()
        self.task_errors = dict()
        self.scene = init_class_by_name(scene[0], scene[1]) if scene else None
        self.task_executor.scene = self.scene
        self.task_executor.trigger_tasks = self.init_tasks(trigger_tasks)
        self.task_executor.onetime_tasks = self.init_tasks(onetime_tasks)
        for task in self.task_executor.trigger_tasks:
            task.post_init()
        for task in self.task_executor.onetime_tasks:
            task.post_init()
        self.load_user_tasks()

    def init_tasks(self, task_classes):
        tasks = []
        for task_class in task_classes:
            task = init_class_by_name(task_class[0], task_class[1], executor=self.task_executor, app=self.app)
            task.after_init(executor=self.task_executor, scene=self.scene)
            from ok.gui.common.config import cfg
            if len(task.supported_languages) == 0 or cfg.get(cfg.language).value.name() in task.supported_languages:
                tasks.append(task)
        return tasks

    def load_user_tasks(self):
        if os.path.exists(self.task_folder):
            if self.task_folder not in sys.path:
                sys.path.append(self.task_folder)
            python_files = glob.glob(os.path.join(self.task_folder, '*.py'))
            logger.info(f"Found tasks: {python_files}")
            for python_file in python_files:
                self.load_single_user_task(python_file)

    def load_single_user_task(self, python_file):
        try:
            instance = self.find_and_instantiate_class(python_file, BaseTask)
            if python_file in self.task_errors:
                del self.task_errors[python_file]
            if instance:
                instance.is_custom = True
                instance.after_init(executor=self.task_executor, scene=self.scene)
                self.task_map[instance] = [python_file, calculate_md5(python_file)]
                if isinstance(instance, TriggerTask):
                    self.task_executor.trigger_tasks.append(instance)
                else:
                    self.task_executor.onetime_tasks.append(instance)
                
                # Update GUI
                from ok.gui.Communicate import communicate
                communicate.task.emit(instance)
                communicate.task_list_updated.emit()
        except Exception as e:
            self.task_errors[python_file] = str(e)
            logger.error(f"Error loading {python_file}: {e}")

    def reload_task_code(self, task):
        python_file, _ = self.task_map.get(task, (None, None))
        if python_file:
            self.unload_task(task)
            module_name = os.path.splitext(os.path.basename(python_file))[0]
            if module_name in sys.modules:
                del sys.modules[module_name]
            self.load_single_user_task(python_file)

    def create_task(self):
        pass

    def unload_task(self, task):
        python_file, _ = self.task_map.get(task, (None, None))
        if python_file is not None:
            del self.task_map[task]
            task.disable()
            if task in self.task_executor.onetime_tasks:
                self.task_executor.onetime_tasks.remove(task)
            if task in self.task_executor.trigger_tasks:
                self.task_executor.trigger_tasks.remove(task)
            from ok.gui.Communicate import communicate
            communicate.task_list_updated.emit()

    def delete_task(self, task):
        python_file, _ = self.task_map.get(task, (None, None))
        if python_file is not None:
            self.unload_task(task)
            if os.path.exists(python_file):
                os.remove(python_file)
            logger.info(f"Deleted task: {python_file}")

    # Function to get class definitions and instantiate subclasses of a given class
    def find_and_instantiate_class(self, file_path, base_class):
        with open(file_path, 'r') as file:
            tree = ast.parse(file.read(), filename=file_path)

        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]

        for cls in classes:
            cls_name = cls.name
            # Find base classes
            base_classes = [base.id for base in cls.bases if isinstance(base, ast.Name)]

            if base_class.__name__ in base_classes or "TriggerTask" in base_classes:
                # Instantiate the class dynamically
                module_name = os.path.splitext(os.path.basename(file_path))[0]
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    cls_obj = getattr(module, cls_name)
                    logger.info(f"Class '{cls_name}' is a subclass of {base_class.__name__}.")
                    try:
                        return cls_obj(executor=self.task_executor, app=self.app)
                    except TypeError:
                        return cls_obj(self.task_executor)
            else:
                logger.info(f"Class '{cls_name}' is not a subclass of {base_class.__name__}.")


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Open the file in binary mode and read it in chunks
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)

    # Return the hexadecimal MD5 checksum
    return md5_hash.hexdigest()
