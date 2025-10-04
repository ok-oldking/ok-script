import ast
import glob
import hashlib
import os.path

from ok import Logger, BaseTask, TriggerTask, og

logger = Logger.get_logger(__name__)


class TaskManager:
    def __init__(self, task_executor, trigger_tasks=[], onetime_tasks=[], scene=None):
        self.task_executor = task_executor
        self.task_folder = os.path.join("user_scripts", "tasks")
        self.has_custom = os.path.exists(self.task_folder)
        self.task_map = dict()
        from ok import init_class_by_name
        self.scene = init_class_by_name(scene[0], scene[1]) if scene else None
        self.task_executor.trigger_tasks = self.init_tasks(trigger_tasks)
        self.task_executor.onetime_tasks = self.init_tasks(onetime_tasks)
        for task in self.task_executor.trigger_tasks:
            task.post_init()
        for task in self.task_executor.onetime_tasks:
            task.post_init()
        self.task_executor.scene = self.scene
        self.load_user_tasks()

    def init_tasks(self, task_classes):
        tasks = []
        from ok import init_class_by_name
        for task_class in task_classes:
            task = init_class_by_name(task_class[0], task_class[1], executor=self.task_executor)
            from ok.gui.common.config import cfg
            if len(task.supported_languages) == 0 or cfg.get(cfg.language).value.name() in task.supported_languages:
                task.set_executor(self)
                task.scene = self.scene
                tasks.append(task)
        return tasks

    def is_custom(self, task):
        return task in self.task_map

    def load_user_tasks(self):
        if os.path.exists('user_scripts'):
            python_files = glob.glob(os.path.join(self.task_folder, '*.py'))
            logger.info(f"Found tasks: {python_files}")
            for python_file in python_files:
                instance = self.find_and_instantiate_class(python_file, BaseTask)
                self.task_map[instance] = [python_file, calculate_md5(python_file)]
                if isinstance(instance, TriggerTask):
                    self.task_executor.trigger_tasks.append(instance)
                else:
                    self.task_executor.onetime_tasks.append(instance)

    def create_task(self):
        pass

    def delete_task(self, task):
        python_file, _ = self.task_map.get(task)
        if python_file is not None:
            os.remove(python_file)
            del self.task_map[task]
            task.disable()
            if task in self.task_executor.onetime_tasks:
                self.task_executor.onetime_tasks.remove(task)
            if task in self.task_executor.trigger_tasks:
                self.task_executor.trigger_tasks.remove(task)
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

            if base_class.__name__ in base_classes:
                # Instantiate the class dynamically
                module_name = file_path.replace('/', '.').replace('\\', '.').replace('.py', '')
                module = __import__(module_name, fromlist=[cls_name])
                cls_obj = getattr(module, cls_name)
                logger.info(f"Class '{cls_name}' is a subclass of {base_class.__name__}.")
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
