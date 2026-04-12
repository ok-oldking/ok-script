import ast
import glob
import hashlib
import importlib
import importlib.util
import inspect
import os.path
import sys

from PySide6.QtCore import QFileSystemWatcher

from ok import og
from ok.task.task import BaseTask, TriggerTask
from ok.util.clazz import init_class_by_name
from ok.util.logger import Logger

try:
    from ok.sandbox.sandbox_runner import SandboxRunner
except ImportError:
    SandboxRunner = None

logger = Logger.get_logger(__name__)


class TaskManager:
    def __init__(self, task_executor, app, trigger_tasks=[], onetime_tasks=[], scene=None):
        self.task_executor = task_executor
        self.app = app
        self.debug = app.debug
        self.custom_tasks_enabled = og.config.get('custom_tasks', False)
        self.task_folder = None
        if self.custom_tasks_enabled:
            self.task_folder = os.path.join(os.getcwd(), 'ok_tasks')
            if not os.path.exists(self.task_folder):
                os.makedirs(self.task_folder)
        self.has_custom = self.custom_tasks_enabled or (self.task_folder and os.path.exists(self.task_folder))
        self._sandbox_runner = None
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
        # Spawn sandbox for custom/imported scripts if needed
        if self.has_custom and SandboxRunner is not None:
            try:
                self._sandbox_runner = SandboxRunner(task_executor, self.task_folder)
                self._sandbox_runner.spawn()
                logger.info("Sandbox process spawned for custom scripts")
            except Exception as e:
                logger.error(f"Failed to spawn sandbox: {e}")
                self._sandbox_runner = None
        if self.debug or self.custom_tasks_enabled:
            self._init_debug_file_watcher()

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
        if self.task_folder and os.path.exists(self.task_folder):
            python_files = glob.glob(os.path.join(self.task_folder, '*.py'))
            logger.info(f"Found tasks: {python_files}")
            if self._sandbox_runner:
                # Load via sandbox — also load in-process for GUI representation
                for python_file in python_files:
                    task_id = os.path.splitext(os.path.basename(python_file))[0]
                    result, error = self._sandbox_runner.load_script(python_file, task_id)
                    if error:
                        self.task_errors[python_file] = error
                        logger.error(f"Sandbox load error {python_file}: {error}")
                    elif result:
                        logger.info(f"Sandbox loaded task {result} from {python_file}")
                # Also load in-process for GUI (task list, enable/disable UI)
                if self.task_folder not in sys.path:
                    sys.path.append(self.task_folder)
                for python_file in python_files:
                    self.load_single_user_task(python_file)
            else:
                if self.task_folder not in sys.path:
                    sys.path.append(self.task_folder)
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
                self._update_debug_watched_files()
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
            self._update_debug_watched_files()

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

        # Load into sandbox if available
        if self._sandbox_runner:
            for python_file in python_files:
                task_id = f"import:{script_name}"
                result, error = self._sandbox_runner.load_script(python_file, task_id)
                if error:
                    self.task_errors[python_file] = error
                    logger.error(f"Sandbox import error {python_file}: {error}")

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

    def _init_debug_file_watcher(self):
        """Initialize file watcher for auto-reloading task files."""
        self._debug_watcher = QFileSystemWatcher()
        self._debug_watcher.fileChanged.connect(self._on_debug_file_changed)
        self._debug_watcher.directoryChanged.connect(self._on_debug_dir_changed)
        self._debug_watched_dirs = []
        self._builtin_task_file_map = {}  # {norm_file_path: [task, ...]}
        self._builtin_file_md5 = {}  # {norm_file_path: md5}
        # Watch ok_tasks folder if custom tasks are enabled
        if self.custom_tasks_enabled:
            ok_tasks_folder = os.path.join(os.getcwd(), 'ok_tasks')
            if os.path.exists(ok_tasks_folder):
                self._debug_watcher.addPath(ok_tasks_folder)
                self._debug_watched_dirs.append(ok_tasks_folder)
        # Watch built-in task source files if in debug mode
        if self.debug:
            self._build_builtin_task_file_map()
        self._update_debug_watched_files()
        logger.info(f"Debug file watcher initialized, watching dirs {self._debug_watched_dirs}, {len(self._debug_watcher.files())} task files")

    def _build_builtin_task_file_map(self):
        """Map source files to built-in task instances for hot-reload."""
        self._builtin_task_file_map = {}
        self._builtin_file_md5 = {}
        for task in self.task_executor.get_all_tasks():
            if getattr(task, 'is_custom', False):
                continue
            try:
                source_file = inspect.getfile(task.__class__)
                norm_path = os.path.normpath(source_file)
                if norm_path not in self._builtin_task_file_map:
                    self._builtin_task_file_map[norm_path] = []
                    self._builtin_file_md5[norm_path] = calculate_md5(source_file)
                self._builtin_task_file_map[norm_path].append(task)
            except (TypeError, OSError):
                pass
        logger.info(f"Built-in task file map: {len(self._builtin_task_file_map)} files")

    def _update_debug_watched_files(self):
        """Sync the file watcher with current task_map and built-in task file entries."""
        if not hasattr(self, '_debug_watcher'):
            return
        current_files = self._debug_watcher.files()
        if current_files:
            self._debug_watcher.removePaths(current_files)
        # Watch custom task files
        for task, (python_file, md5) in self.task_map.items():
            if os.path.exists(python_file):
                self._debug_watcher.addPath(python_file)
        # Watch built-in task source files
        for file_path in self._builtin_task_file_map:
            if os.path.exists(file_path):
                self._debug_watcher.addPath(file_path)

    def _on_debug_file_changed(self, path):
        """Handle task file changes: reload custom or built-in tasks."""
        if not os.path.exists(path):
            return
        norm_path = os.path.normpath(path)
        file_name = os.path.basename(path)
        reloaded = False

        # Check custom tasks (task_map)
        for task, (python_file, old_md5) in list(self.task_map.items()):
            if os.path.normpath(python_file) == norm_path:
                new_md5 = calculate_md5(path)
                if new_md5 != old_md5:
                    logger.info(f"Debug file watcher: reloading custom task {file_name}")
                    self.reload_task_code(task)
                    from ok.gui.util.Alert import alert_info
                    alert_info(f"Task reloaded: {file_name}", tray=True)
                    reloaded = True
                break

        # Check built-in tasks
        if not reloaded and norm_path in self._builtin_task_file_map:
            old_md5 = self._builtin_file_md5.get(norm_path)
            new_md5 = calculate_md5(path)
            if new_md5 != old_md5:
                tasks = list(self._builtin_task_file_map[norm_path])
                for task in tasks:
                    self._reload_builtin_task(task)
                self._build_builtin_task_file_map()
                from ok.gui.util.Alert import alert_info
                alert_info(f"Task reloaded: {file_name}")

        # Re-add path (some editors delete & recreate files on save)
        self._update_debug_watched_files()

    def _reload_builtin_task(self, task):
        """Reload a built-in task by reloading its module and replacing the instance."""
        module_name = task.__class__.__module__
        class_name = task.__class__.__name__

        is_trigger = task in self.task_executor.trigger_tasks
        task_list = self.task_executor.trigger_tasks if is_trigger else self.task_executor.onetime_tasks
        try:
            index = task_list.index(task)
        except ValueError:
            logger.error(f"Built-in task {class_name} not found in task list")
            return

        try:
            module = sys.modules.get(module_name)
            if module:
                importlib.reload(module)
            else:
                module = importlib.import_module(module_name)

            cls = getattr(module, class_name)
            new_task = cls(executor=self.task_executor, app=self.app)
            new_task.after_init(executor=self.task_executor, scene=self.scene)
            new_task.post_init()

            task_list[index] = new_task

            from ok.gui.Communicate import communicate
            communicate.task.emit(new_task)
            communicate.task_list_updated.emit()
            logger.info(f"Reloaded built-in task {class_name}")
        except Exception as e:
            logger.error(f"Failed to reload built-in task {class_name}: {e}")

    def _on_debug_dir_changed(self, path):
        """Handle new .py files appearing in a watched task directory."""
        if not os.path.exists(path):
            return
        existing_files = {os.path.normpath(data[0]) for task, data in self.task_map.items()}
        for file in os.listdir(path):
            if file.endswith('.py'):
                full_path = os.path.join(path, file)
                if os.path.normpath(full_path) not in existing_files:
                    logger.info(f"Debug file watcher: new task file detected {file} in {path}")
                    instance = self.load_single_user_task(full_path)
                    if instance:
                        from ok.gui.util.Alert import alert_info
                        alert_info(f"New task loaded: {file}")
        self._update_debug_watched_files()

    # Function to get class definitions and instantiate subclasses of a given class
    def cleanup(self):
        """Shut down the sandbox process."""
        if self._sandbox_runner:
            self._sandbox_runner.shutdown()
            self._sandbox_runner = None

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
