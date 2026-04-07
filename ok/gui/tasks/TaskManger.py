import ast
import glob
import hashlib
import importlib.util
import os.path
import sys

from ok import og
from ok.task.task import BaseTask, TriggerTask
from ok.util.clazz import init_class_by_name
from ok.util.logger import Logger

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
        self.imported_scripts = {}  # {file_name: {'folder': ..., 'script_name': ..., 'tasks': [...]}}
        self.scene = init_class_by_name(scene[0], scene[1]) if scene else None
        self.task_executor.scene = self.scene
        self.task_executor.trigger_tasks = self.init_tasks(trigger_tasks)
        self.task_executor.onetime_tasks = self.init_tasks(onetime_tasks)
        for task in self.task_executor.trigger_tasks:
            task.post_init()
        for task in self.task_executor.onetime_tasks:
            task.post_init()
        self.load_user_tasks()
        self.load_imported_tasks()

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

    def load_single_user_task(self, python_file, import_namespace=None):
        try:
            instance = self.find_and_instantiate_class(python_file, BaseTask)
            if python_file in self.task_errors:
                del self.task_errors[python_file]
            if instance:
                instance.is_custom = True
                if import_namespace:
                    instance.import_namespace = import_namespace
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
                return instance
        except Exception as e:
            self.task_errors[python_file] = str(e)
            logger.error(f"Error loading {python_file}: {e}")
        return None

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

    def load_imported_tasks(self):
        """Scan ok_import/ folder and load all valid imported scripts."""
        from ok.gui.tasks.ScriptPackager import scan_import_folders
        imports = scan_import_folders()
        for imp in imports:
            if imp['file_name'] not in self.imported_scripts:
                self._load_import_entry(imp)

    def disable_all_scripts(self):
        """Disable all one-time tasks, custom tasks, and imported tasks while keeping built-in trigger tasks unchanged."""
        logger.info("Disabling all onetime, custom, and imported tasks before import.")
        
        # Disable all one-time tasks (built-in, custom, and imported)
        for task in list(self.task_executor.onetime_tasks or []):
            task.disable()
            
        # Disable custom and imported trigger tasks
        for task in list(self.task_executor.trigger_tasks or []):
            if getattr(task, 'is_custom', False) or getattr(task, 'import_namespace', None):
                task.disable()

    def load_import_folder(self, import_folder):
        """Load tasks from a specific import folder (called after import)."""
        self.disable_all_scripts()
        from ok.gui.tasks.ScriptPackager import scan_import_folders
        imports = scan_import_folders()
        for imp in imports:
            if os.path.normpath(imp['folder']) == os.path.normpath(import_folder):
                # Unload existing if re-importing
                if imp['file_name'] in self.imported_scripts:
                    old_tasks = self.imported_scripts[imp['file_name']].get('tasks', [])
                    for task in old_tasks:
                        self.unload_task(task)
                self._load_import_entry(imp)
                return

    def _load_import_entry(self, imp):
        """Load a single import entry."""
        folder = imp['folder']
        file_name = imp['file_name']
        script_name = imp['script_name']

        if folder not in sys.path:
            sys.path.append(folder)

        loaded_tasks = []
        python_files = glob.glob(os.path.join(folder, '*.py'))
        logger.info(f"Loading imported script '{script_name}' from {folder}, files: {python_files}")

        for python_file in python_files:
            task = self.load_single_user_task(python_file, import_namespace=file_name)
            if task:
                task.group_name = script_name
                loaded_tasks.append(task)

        self.imported_scripts[file_name] = {
            'folder': folder,
            'script_name': script_name,
            'version': imp.get('version', ''),
            'tasks': loaded_tasks,
            'has_features': imp.get('has_features', False)
        }

        # Reload features if available (FeatureSet.process_data scans ok_import)
        if imp.get('has_features', False):
            self._reload_features()

        from ok.gui.Communicate import communicate
        communicate.task_list_updated.emit()

    def _reload_features(self):
        """Trigger FeatureSet to reload data, which now includes ok_import scanning."""
        if self.task_executor.feature_set is None:
            return

        try:
            fs = self.task_executor.feature_set
            # Safely check for width/height attributes if available
            if getattr(fs, 'width', 0) > 0 and getattr(fs, 'height', 0) > 0:
                fs.process_data()
                logger.info('Reloaded feature_set data.')
        except Exception as e:
            logger.error(f'Failed to reload features: {e}')

    def delete_imported_script(self, file_name):
        """Unload and delete an imported script folder."""
        if file_name in self.imported_scripts:
            import shutil
            imp = self.imported_scripts[file_name]
            # Disable and unload tasks
            tasks_to_unload = list(imp.get('tasks', []))
            for task in tasks_to_unload:
                task.disable()
                self.unload_task(task)
            
            # Remove from imported mapping
            del self.imported_scripts[file_name]
            
            # Remove folder
            folder = imp['folder']
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                    logger.info(f"Deleted imported script folder: {folder}")
                except Exception as e:
                    logger.error(f"Failed to delete {folder}: {e}")
            
            # Trigger features reload to remove namespaced features
            self._reload_features()
            
            from ok.gui.Communicate import communicate
            communicate.task_list_updated.emit()
    # Function to get class definitions and instantiate subclasses of a given class
    def find_and_instantiate_class(self, file_path, base_class):
        with open(file_path, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=file_path)

        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

        if not classes:
            return None

        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for cls_name in classes:
                cls_obj = getattr(module, cls_name, None)
                if cls_obj and isinstance(cls_obj, type):
                    if issubclass(cls_obj, base_class) or issubclass(cls_obj, TriggerTask):
                        logger.info(f"Class '{cls_name}' is a subclass of {base_class.__name__}.")
                        try:
                            return cls_obj(executor=self.task_executor, app=self.app)
                        except TypeError:
                            return cls_obj(self.task_executor)
                    else:
                        logger.info(f"Class '{cls_name}' is not a subclass of {base_class.__name__}.")
        return None


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Open the file in binary mode and read it in chunks
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)

    # Return the hexadecimal MD5 checksum
    return md5_hash.hexdigest()
