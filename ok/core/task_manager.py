import ast
import glob
import hashlib
import importlib
import importlib.util
import inspect
import os.path
import sys
import time
from pathlib import Path
from types import ModuleType

from ok import og
from ok.core.events import communicate
from ok.task.task import BaseTask, TriggerTask
from ok.util.clazz import init_class_by_name
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class TaskManager:
    def __init__(self, task_executor, app, trigger_tasks=None, onetime_tasks=None, scene=None,
                 file_watcher_factory=None, defer_plugin_validation=False):
        self.task_executor = task_executor
        self.app = app
        self.debug = app.debug
        # Accept the legacy factory argument without creating any watchers.
        self.defer_plugin_validation = defer_plugin_validation or file_watcher_factory is not None
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

    def load_single_user_task(self, python_file, import_namespace=None, task_class=None, register=True):
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
                instance.post_init()
                if not register:
                    return instance
                self._register_custom_task(instance, python_file)
                
                # Update GUI
                communicate.task.emit(instance)
                communicate.task_list_updated.emit()
                return instance
        except Exception as e:
            if instance is not None:
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
        """Queue a reload of a task and any tasks sharing its module/plugin."""
        return self.reload_tasks([task])

    def reload_tasks(self, tasks=None):
        """Queue task instances or classes for reload; None reloads all tasks.

        Returns an ExecutorJob whose future resolves to the replacement tasks.
        Do not wait on that future from task code: the reload runs after the
        current task/job returns. Module siblings and whole plugins reload
        together so they share a single revision of their classes and state.
        """
        requested = None if tasks is None else tuple(tasks)
        return self.task_executor.submit(
            lambda: self._dispatch_reload(requested), name='reload_tasks')

    def _dispatch_reload(self, tasks):
        # The Qt adapter marshals this operation to the GUI thread while the
        # executor job waits, preventing scheduled tasks from running meanwhile.
        return self._reload_tasks(tasks)

    def _register_custom_task(self, task, python_file):
        self.task_map[task] = [python_file, calculate_md5(python_file)]
        task_list = (self.task_executor.trigger_tasks if isinstance(task, TriggerTask)
                     else self.task_executor.onetime_tasks)
        task_list.append(task)

    @staticmethod
    def _class_key(cls):
        return cls.__module__, cls.__qualname__

    @staticmethod
    def _load_source_module(module_name, file_path):
        """Compile source directly, including same-size, same-timestamp edits."""
        if module_name in {'__main__', '__mp_main__'}:
            raise ValueError('Move task classes into an importable module before reloading')
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load task module {module_name} from {file_path}')
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            exec(compile(Path(file_path).read_bytes(), str(file_path), 'exec'), module.__dict__)
        except BaseException:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
            raise
        parent_name, _, attribute = module_name.rpartition('.')
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], attribute, module)
        return module

    def _reload_tasks(self, requested=None):
        from ok.core.plugins import forget_plugin_modules
        from ok.core.script_packager import scan_import_folders

        all_tasks = list(self.task_executor.onetime_tasks) + list(self.task_executor.trigger_tasks)
        if requested is None:
            selected = all_tasks
            namespaces = set(self.imported_scripts)
        else:
            selected = []
            namespaces = set()
            for item in requested:
                if not isinstance(item, BaseTask) and not (
                        isinstance(item, type) and issubclass(item, BaseTask)):
                    raise TypeError('reload_tasks expects a list of task instances or classes')
                key = self._class_key(item if isinstance(item, type) else type(item))
                matches = [task for task in all_tasks if self._class_key(type(task)) == key]
                if not matches:
                    raise ValueError(f'Task is not registered: {key[0]}.{key[1]}')
                selected.extend(matches)
        for task in selected:
            namespace = getattr(task, 'import_namespace', None)
            if namespace in self.imported_scripts:
                namespaces.add(namespace)

        module_names = {type(task).__module__ for task in selected
                        if getattr(task, 'import_namespace', None) not in self.imported_scripts}
        normal_tasks = [task for task in all_tasks if type(task).__module__ in module_names
                        and getattr(task, 'import_namespace', None) not in self.imported_scripts]
        plugin_entries = {name: self.imported_scripts[name] for name in namespaces}
        affected = normal_tasks + [task for entry in plugin_entries.values() for task in entry['tasks']]
        if self.task_executor.current_task in affected:
            raise RuntimeError('Task reload must run after the current task has finished')

        # Snapshot modules so a failed import/initialization leaves the running
        # registry and the original module objects intact.
        originals = {name: sys.modules.get(name) for name in module_names}
        for name, module in tuple(sys.modules.items()):
            source = getattr(module, '__file__', None)
            if source and any(Path(source).resolve().is_relative_to(Path(entry['folder']).resolve())
                              for entry in plugin_entries.values()):
                originals[name] = module
            elif any(name == '_ok_plugin_' + hashlib.sha256(str(Path(entry['folder']).resolve()).encode()).hexdigest()[:16]
                     for entry in plugin_entries.values()):
                originals[name] = module
        before_names = set(sys.modules)
        replacements = {}
        prepared_plugins = {}
        candidates = []
        current_file = None
        try:
            importlib.invalidate_caches()
            # Reload dependencies before consumers when registered task modules
            # import one another. Each module executes only once per request.
            pending = set(module_names)
            ordered = []
            visiting = set()

            def visit(name):
                if name not in pending or name in visiting:
                    return
                visiting.add(name)
                module = originals[name]
                for value in vars(module).values() if module is not None else ():
                    dependency = value.__name__ if isinstance(value, ModuleType) else getattr(value, '__module__', None)
                    if isinstance(dependency, str) and dependency != name:
                        visit(dependency)
                visiting.remove(name)
                pending.remove(name)
                ordered.append(name)

            for name in sorted(module_names):
                visit(name)
            modules = {}
            for name in ordered:
                old = next(task for task in normal_tasks if type(task).__module__ == name)
                current_file = self.task_map[old][0] if old in self.task_map else inspect.getfile(type(old))
                modules[name] = self._load_source_module(name, current_file)
            for old in normal_tasks:
                current_file = self.task_map[old][0] if old in self.task_map else inspect.getfile(type(old))
                cls = getattr(modules[type(old).__module__], type(old).__name__)
                if not isinstance(cls, type) or not issubclass(cls, BaseTask):
                    raise TypeError('Reloaded tasks must extend BaseTask')
                if issubclass(cls, TriggerTask) != isinstance(old, TriggerTask):
                    raise TypeError('Reload cannot change a task between one-time and trigger types')
                new = self._instantiate_task(cls)
                candidates.append(new)
                new.after_init(executor=self.task_executor, scene=self.scene)
                new.post_init()
                if old in self.task_map:
                    new.is_custom = True
                replacements[old] = new

            imports = {imp['file_name']: imp for imp in scan_import_folders()} if namespaces else {}
            for namespace, entry in plugin_entries.items():
                current_file = None
                if namespace not in imports:
                    raise ValueError(f'Plugin folder does not contain a valid manifest: {namespace}')
                forget_plugin_modules(entry['folder'])
                # Bypass timestamp-based bytecode for all plugin entry/helper modules.
                for cached in Path(entry['folder']).rglob('*.pyc'):
                    cached.unlink()
                prepared = self._prepare_import_entry(imports[namespace])
                candidates.extend(prepared['tasks'])
                if prepared['errors']:
                    raise RuntimeError('\n'.join(prepared['errors']))
                prepared_plugins[namespace] = prepared
        except BaseException as error:
            for task in reversed(candidates):
                self._destroy_task(task)
            for name in set(sys.modules) - before_names:
                module = sys.modules[name]
                source = getattr(module, '__file__', None)
                if name in module_names or source and any(
                        Path(source).resolve().is_relative_to(Path(entry['folder']).resolve())
                        for entry in plugin_entries.values()):
                    sys.modules.pop(name, None)
            for name, module in originals.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
                    parent_name, _, attribute = name.rpartition('.')
                    if parent_name in sys.modules:
                        setattr(sys.modules[parent_name], attribute, module)
            if current_file is not None:
                self.task_errors[current_file] = str(error)
            raise

        # Remove pages on the GUI thread before closing task-owned services.
        for namespace in prepared_plugins:
            self.imported_scripts.pop(namespace)
        if prepared_plugins:
            communicate.task_list_updated.emit()
        enabled_triggers = {old: old.enabled for old in affected if isinstance(old, TriggerTask)}
        for old in affected:
            try:
                old.disable()
            except Exception as error:
                logger.error('Failed to disable old task during reload', error)
            self._destroy_task(old)
        for task_list in (self.task_executor.onetime_tasks, self.task_executor.trigger_tasks):
            task_list[:] = [replacements.get(task, task) for task in task_list
                            if getattr(task, 'import_namespace', None) not in prepared_plugins]
        for old, new in replacements.items():
            if old in enabled_triggers:
                new._enabled = enabled_triggers[old]
                new.config['_enabled'] = enabled_triggers[old]
            if old in self.task_map:
                python_file, _ = self.task_map.pop(old)
                self.task_map[new] = [python_file, calculate_md5(python_file)]
            else:
                python_file = inspect.getfile(type(new))
            self.task_errors.pop(python_file, None)
        for namespace, entry in prepared_plugins.items():
            for new in entry['tasks']:
                old = next((task for task in plugin_entries[namespace]['tasks']
                            if self._class_key(type(task)) == self._class_key(type(new))), None)
                if old in enabled_triggers and isinstance(new, TriggerTask):
                    new._enabled = enabled_triggers[old]
                    new.config['_enabled'] = enabled_triggers[old]
            for old in plugin_entries[namespace]['tasks']:
                self.task_map.pop(old, None)
            self._register_import_entry(namespace, entry)
        self.task_executor.trigger_task_index = -1
        communicate.task_list_updated.emit()
        return list(replacements.values()) + [task for entry in prepared_plugins.values() for task in entry['tasks']]

    @staticmethod
    def _destroy_task(task):
        try:
            task.on_destroy()
        except Exception as error:
            logger.error('Failed to close task', error)

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
            self._destroy_task(task)

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
        entry = self._prepare_import_entry(imp)
        self._register_import_entry(imp['file_name'], entry)
        communicate.task_list_updated.emit()

    def _prepare_import_entry(self, imp):
        """Initialize plugin tasks without exposing a partial replacement."""
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
            task = self.load_single_user_task(python_file, import_namespace=file_name, register=False)
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
                        python_file, import_namespace=file_name, task_class=task_class, register=False)
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

        return {
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

    def _register_import_entry(self, file_name, entry):
        self.imported_scripts[file_name] = entry
        for task in entry['tasks']:
            self._register_custom_task(task, inspect.getfile(type(task)))
        from ok.core.plugin_staging import finish_plugin_update
        if entry['errors']:
            finish_plugin_update(file_name, error='\n'.join(entry['errors']))
        elif not getattr(self, 'defer_plugin_validation', False):
            finish_plugin_update(file_name)

        # Reload features if available (FeatureSet.process_data scans ok_import)
        if entry.get('has_features', False):
            self._reload_features()

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

    # Function to get class definitions and instantiate subclasses of a given class
    def find_and_instantiate_class(self, file_path, base_class):
        with open(file_path, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=file_path)

        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

        if not classes:
            return None

        module_name = os.path.splitext(os.path.basename(file_path))[0]
        module = self._load_source_module(module_name, file_path)

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
            inspect.signature(cls).bind(executor=self.task_executor, app=self.app)
        except TypeError:
            return cls(self.task_executor)
        return cls(executor=self.task_executor, app=self.app)


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Open the file in binary mode and read it in chunks
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)

    # Return the hexadecimal MD5 checksum
    return md5_hash.hexdigest()
