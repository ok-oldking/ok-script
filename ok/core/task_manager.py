import ast
import glob
import hashlib
import importlib
import importlib.util
import inspect
import os.path
import sys
import time

from ok import og
from ok.core.events import communicate
from ok.core.notifications import alert_info
from ok.task.task import BaseTask, TriggerTask
from ok.util.clazz import init_class_by_name
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class TaskManager:
    def __init__(self, task_executor, app, trigger_tasks=None, onetime_tasks=None, scene=None,
                 file_watcher_factory=None):
        self.task_executor = task_executor
        self.app = app
        self.debug = app.debug
        self.file_watcher_factory = file_watcher_factory
        self.custom_tasks_enabled = og.config.get('custom_tasks', False)
        self.task_folder = None
        if self.custom_tasks_enabled:
            self.task_folder = os.path.join(os.getcwd(), 'ok_tasks')
            if not os.path.exists(self.task_folder):
                os.makedirs(self.task_folder)
        self.has_custom = self.custom_tasks_enabled or (self.task_folder and os.path.exists(self.task_folder))
        self.task_map = dict()
        self.task_errors = dict()
        self.imported_scripts = {}  # {file_name: {'folder': ..., 'script_name': ..., 'tasks': [...]}}
        self.scene = init_class_by_name(scene[0], scene[1]) if scene else None
        self.task_executor.scene = self.scene
        self.task_executor.trigger_tasks = self.init_tasks(trigger_tasks or [])
        self.task_executor.onetime_tasks = self.init_tasks(onetime_tasks or [])
        for task in self.task_executor.trigger_tasks:
            task.post_init()
        for task in self.task_executor.onetime_tasks:
            task.post_init()
        self.load_user_tasks()
        self.load_imported_tasks()
        if (self.debug or self.custom_tasks_enabled) and self.file_watcher_factory is not None:
            self._init_debug_file_watcher()

    def init_tasks(self, task_classes):
        tasks = []
        for task_class in task_classes:
            task = init_class_by_name(task_class[0], task_class[1], executor=self.task_executor, app=self.app)
            task.after_init(executor=self.task_executor, scene=self.scene)
            locale = self.app.locale
            locale_name = locale.name() if hasattr(locale, "name") else str(locale)
            if len(task.supported_languages) == 0 or locale_name in task.supported_languages:
                tasks.append(task)
        return tasks

    def load_user_tasks(self):
        if self.task_folder and os.path.exists(self.task_folder):
            if self.task_folder not in sys.path:
                sys.path.append(self.task_folder)
            python_files = glob.glob(os.path.join(self.task_folder, '*.py'))
            logger.info(f"Found tasks: {python_files}")
            for python_file in python_files:
                self.load_single_user_task(python_file)

    def load_single_user_task(self, python_file, import_namespace=None, task_class=None):
        instance = None
        try:
            if task_class is not None:
                if not isinstance(task_class, type) or not issubclass(task_class, BaseTask):
                    raise TypeError('Plugin tasks must extend BaseTask')
                instance = self._instantiate_task(task_class)
            else:
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
                communicate.task.emit(instance)
                communicate.task_list_updated.emit()
                self._update_debug_watched_files()
                return instance
        except Exception as e:
            if import_namespace is not None and instance is not None:
                for registered in tuple(self.task_map):
                    if registered is instance:
                        del self.task_map[registered]
                for tasks in (self.task_executor.onetime_tasks, self.task_executor.trigger_tasks):
                    tasks[:] = [task for task in tasks if task is not instance]
                try:
                    instance.on_destroy()
                except Exception as error:
                    logger.error('Failed to close partially initialized plugin task', error)
            self.task_errors[python_file] = str(e)
            logger.error(f"Error loading {python_file}: {e}")
        return None

    def reload_task_code(self, task):
        python_file, _ = self.task_map.get(task, (None, None))
        if python_file:
            namespace = getattr(task, 'import_namespace', None)
            if namespace in self.imported_scripts:
                # A plugin's tabs and tasks share module/runtime state. Replace
                # the whole entry so GUI pages cannot retain an unloaded task.
                self.load_import_folder(self.imported_scripts[namespace]['folder'])
                return
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
            try:
                task.disable()
            except Exception as error:
                logger.error('Failed to disable plugin task', error)
            if task in self.task_executor.onetime_tasks:
                self.task_executor.onetime_tasks.remove(task)
            if task in self.task_executor.trigger_tasks:
                self.task_executor.trigger_tasks.remove(task)
            namespace = getattr(task, 'import_namespace', None)
            entry = self.imported_scripts.get(namespace)
            if entry is not None:
                entry['tasks'] = [current for current in entry['tasks'] if current is not task]
            communicate.task_list_updated.emit()
            if namespace is not None:
                try:
                    task.on_destroy()
                except Exception as error:
                    logger.error('Failed to close plugin task', error)
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
        from ok.core.script_packager import scan_import_folders
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
        from ok.core.script_packager import scan_import_folders
        imports = scan_import_folders()
        for imp in imports:
            if os.path.normpath(imp['folder']) == os.path.normpath(import_folder):
                # Unload existing if re-importing
                if imp['file_name'] in self.imported_scripts:
                    self.unload_imported_script(imp['file_name'])
                self._load_import_entry(imp)
                return self.imported_scripts[imp['file_name']]
        raise ValueError('Plugin folder does not contain a valid manifest')

    def _load_import_entry(self, imp):
        """Load a single import entry."""
        folder = imp['folder']
        file_name = imp['file_name']
        script_name = imp['script_name']

        if folder not in sys.path:
            sys.path.append(folder)

        loaded_tasks = []
        errors = []
        declared_tasks = imp.get('tasks')
        python_files = glob.glob(os.path.join(folder, '*.py')) if declared_tasks is None else []
        tab_modules = {spec[0] + '.py' for spec in imp.get('custom_tabs', []) if '.' not in spec[0]}
        python_files = [path for path in python_files if os.path.basename(path) not in tab_modules]
        logger.info(f"Loading imported script '{script_name}' from {folder}, files: {python_files}")

        for python_file in python_files:
            task = self.load_single_user_task(python_file, import_namespace=file_name)
            if task:
                task.group_name = script_name
                loaded_tasks.append(task)

        if declared_tasks is not None:
            from ok.core.plugins import import_plugin_class
            for specification in declared_tasks:
                try:
                    task_class = import_plugin_class(folder, specification)
                    python_file = inspect.getfile(task_class)
                    task = self.load_single_user_task(
                        python_file, import_namespace=file_name, task_class=task_class)
                    if task is not None:
                        task.group_name = script_name
                        loaded_tasks.append(task)
                except Exception as error:
                    errors.append(f'{specification[0]}.{specification[1]}: {error}')
                    logger.error('Failed to load plugin task', error)

        from pathlib import Path
        for python_file, error in self.task_errors.items():
            if Path(python_file).resolve().is_relative_to(Path(folder).resolve()):
                errors.append(f'{os.path.basename(python_file)}: {error}')

        self.imported_scripts[file_name] = {
            'folder': folder,
            'script_name': script_name,
            'version': imp.get('version', ''),
            'tasks': loaded_tasks,
            'custom_tabs': imp.get('custom_tabs', []),
            'errors': errors,
            'tab_errors': {},
            'loaded_at': time.monotonic(),
            'has_features': imp.get('has_features', False)
        }

        from ok.core.plugin_staging import finish_plugin_update
        if errors:
            finish_plugin_update(file_name, error='\n'.join(errors))
        elif getattr(self, 'file_watcher_factory', None) is None:
            finish_plugin_update(file_name)

        # Reload features if available (FeatureSet.process_data scans ok_import)
        if imp.get('has_features', False):
            self._reload_features()

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

    def unload_imported_script(self, file_name):
        """Detach GUI pages before closing their task-owned background services."""
        from ok.core.plugins import forget_plugin_modules
        imp = self.imported_scripts.pop(file_name, None)
        if imp is None:
            return
        communicate.task_list_updated.emit()
        for task in tuple(imp.get('tasks', ())):
            self.unload_task(task)
        folder = imp['folder']
        if folder in sys.path:
            sys.path.remove(folder)
        forget_plugin_modules(folder)
        communicate.task_list_updated.emit()
        return imp

    def delete_imported_script(self, file_name):
        """Queue deletion for the next launch, leaving live code/resources alone."""
        from pathlib import Path
        from ok.core.plugin_staging import stage_plugin_delete
        from ok.core.script_packager import get_ok_import_folder
        imp = self.imported_scripts.get(file_name)
        folder = Path(imp['folder'] if imp else Path(get_ok_import_folder()) / file_name).resolve()
        base = Path(get_ok_import_folder()).resolve()
        if folder.parent != base or folder.name != file_name:
            raise ValueError('Plugin folder must be directly inside ok_import')
        change = stage_plugin_delete(file_name)
        return change

    def _init_debug_file_watcher(self):
        """Initialize file watcher for auto-reloading task files."""
        self._debug_watcher = self.file_watcher_factory()
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
        logger.info(f"Debug file watcher initialized, watching dirs {self._debug_watched_dirs}")

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
        """Sync the file watcher with current task folders."""
        if not hasattr(self, '_debug_watcher'):
            return
        
        # Watch custom task folders
        for task, (python_file, md5) in self.task_map.items():
            if os.path.exists(python_file):
                folder = os.path.dirname(python_file)
                if folder not in self._debug_watched_dirs:
                    self._debug_watcher.addPath(folder)
                    self._debug_watched_dirs.append(folder)
        # Watch built-in task source folders
        for file_path in self._builtin_task_file_map:
            if os.path.exists(file_path):
                folder = os.path.dirname(file_path)
                if folder not in self._debug_watched_dirs:
                    self._debug_watcher.addPath(folder)
                    self._debug_watched_dirs.append(folder)

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

            communicate.task.emit(new_task)
            communicate.task_list_updated.emit()
            logger.info(f"Reloaded built-in task {class_name}")
        except Exception as e:
            logger.error(f"Failed to reload built-in task {class_name}: {e}")

    def _on_debug_dir_changed(self, path):
        """Handle new .py files appearing in a watched task directory or modifications."""
        if not os.path.exists(path):
            return
        existing_files = {os.path.normpath(data[0]) for task, data in self.task_map.items()}
        for file in os.listdir(path):
            if file.endswith('.py'):
                full_path = os.path.join(path, file)
                norm_full_path = os.path.normpath(full_path)
                if norm_full_path not in existing_files and norm_full_path not in self._builtin_task_file_map:
                    logger.info(f"Debug file watcher: new task file detected {file} in {path}")
                    instance = self.load_single_user_task(full_path)
                    if instance:
                        alert_info(f"New task loaded: {file}")
                else:
                    self._on_debug_file_changed(full_path)
        self._update_debug_watched_files()

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
                        return self._instantiate_task(cls_obj)
                    else:
                        logger.info(f"Class '{cls_name}' is not a subclass of {base_class.__name__}.")
        return None

    def _instantiate_task(self, cls):
        try:
            return cls(executor=self.task_executor, app=self.app)
        except TypeError:
            return cls(self.task_executor)


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Open the file in binary mode and read it in chunks
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)

    # Return the hexadecimal MD5 checksum
    return md5_hash.hexdigest()
