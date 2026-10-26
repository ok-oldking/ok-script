"""File-based development tasks, independent of the MCP transport and Qt."""

import hashlib
import importlib.util
import inspect
import json
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import CancelledError
from pathlib import Path

from ok.core.code_runner import capture_output
from ok.task.exceptions import TaskDisabledException
from ok.task.task import BaseTask, TriggerTask


TERMINAL_STATES = {'succeeded', 'failed', 'cancelled'}


class McpTaskRunner:
    """Run one development file at a time on the existing executor.

    A file must define ``class Task(BaseTask)`` with ``reset_to_start()``,
    ``verify_start_state()`` and ``run()``. Hooks may assert or return False
    to reject the attempt. No task is added to the regular scheduler.
    """

    def __init__(self, executor, app, screenshot_service, artifact_directory='logs/mcp', prepare=None):
        self.executor = executor
        self.app = app
        self.screenshot_service = screenshot_service
        self.artifact_directory = Path(artifact_directory).resolve()
        self.prepare = prepare
        self._lock = threading.RLock()
        self._runs = {}
        self._active = None
        self._observation_job = None
        self._closed = False
        self.executor.enable_frame_snapshots()

    def _save(self, record):
        path = Path(record['artifact_directory']) / 'status.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
        temporary.replace(path)

    def _phase(self, run_id, phase):
        self.executor.check_enabled()
        with self._lock:
            record = self._runs[run_id]['record']
            record['phase'] = phase
            if record['state'] != 'stopping':
                record['state'] = 'running'
            self._save(record)

    def run_task(self, file_path: str):
        """Load a current file revision and return immediately with its run ID."""
        path = Path(file_path).resolve(strict=True)
        if path.suffix.lower() != '.py' or not path.is_file():
            raise ValueError('file_path must point to a Python task file')
        source = path.read_bytes()
        with self._lock:
            if self._closed:
                raise RuntimeError('MCP task runner is shutting down')
            if self._active is not None:
                raise RuntimeError(f'Run {self._active} is still active; wait until it has stopped')
            run_id = uuid.uuid4().hex
            owner = f'mcp:{run_id}'
            self.executor.acquire_exclusive(owner)
            try:
                directory = self.artifact_directory / run_id
                directory.mkdir(parents=True)
                record = {
                    'run_id': run_id, 'file_path': str(path),
                    'source_sha256': hashlib.sha256(source).hexdigest(),
                    'state': 'queued', 'phase': 'loading', 'created_at': time.time(),
                    'finished_at': None, 'error': None, 'result': None,
                    'artifact_directory': str(directory), 'log_path': str(directory / 'run.log'),
                    'screenshots_directory': str(Path(self.screenshot_service.screenshot_folder).resolve()),
                }
                self._runs[run_id] = {'record': record, 'job': None}
                self._active = run_id
                self._save(record)
                job = self.executor.submit(
                    lambda: self._execute(run_id, path, source), name=f'mcp:{path.name}', owner=owner)
                self._runs[run_id]['job'] = job
                job.future.add_done_callback(lambda future: self._finished(run_id, owner, future))
            except BaseException:
                self._active = None
                self._runs.pop(run_id, None)
                self.executor.release_exclusive(owner)
                raise
            return dict(record)

    def _execute(self, run_id, path, source):
        directory = Path(self._runs[run_id]['record']['artifact_directory'])
        module_name = f'_ok_mcp_task_{run_id}'
        # Keep sibling imports available through run() and on_destroy(), too.
        added_path = str(path.parent) not in sys.path
        task = None
        if added_path:
            sys.path.insert(0, str(path.parent))
        try:
            with (directory / 'run.log').open('a', encoding='utf-8', buffering=1) as output:
                with capture_output(output.write):
                    try:
                        self._phase(run_id, 'loading')
                        spec = importlib.util.spec_from_file_location(module_name, path)
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        # Compile the bytes directly: same-size edits within a second must
                        # not pick up stale .pyc files on the next attempt.
                        exec(compile(source, str(path), 'exec'), module.__dict__)
                        cls = getattr(module, 'Task', None)
                        if (not isinstance(cls, type) or cls.__module__ != module_name
                                or not issubclass(cls, BaseTask) or issubclass(cls, TriggerTask)):
                            raise TypeError('File must define class Task(BaseTask), not a TriggerTask')
                        for method in ('reset_to_start', 'verify_start_state', 'run'):
                            fn = getattr(cls, method, None)
                            if (not callable(fn) or inspect.iscoroutinefunction(fn)
                                    or inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn)):
                                raise TypeError(f'Task must implement synchronous {method}()')
                        if cls.run is BaseTask.run:
                            raise TypeError('Task must implement run()')
                        task = cls(executor=self.executor, app=self.app)
                        task.artifact_directory = directory
                        task.after_init(executor=self.executor, scene=self.executor.scene)
                        task.post_init()
                        task._enabled = True
                        task.running = True
                        task.start_time = time.time()
                        self.executor.current_task = task
                        self._phase(run_id, 'preparing')
                        if self.prepare is not None:
                            self.prepare()
                        task.ensure_capture()
                        self.executor._prepare_task_for_run(is_trigger_task=False)
                        self._phase(run_id, 'resetting')
                        if task.reset_to_start() is False:
                            raise RuntimeError('reset_to_start() returned False')
                        self._phase(run_id, 'verifying_start')
                        verified = task.verify_start_state()
                        if verified is not None and verified is not True:
                            raise RuntimeError('verify_start_state() must assert or return True')
                        self._phase(run_id, 'running')
                        result = task.run()
                        if result is False:
                            raise RuntimeError('Task.run() returned False')
                        self.executor.check_enabled()
                        return None if result is None else repr(result)[:2000]
                    finally:
                        if self.executor.current_task is task:
                            self.executor.current_task = None
                        if task is not None:
                            task.running = False
                            task._enabled = False
                            # Cleanup must finish before the job resolves and ownership
                            # is released, including when reset or verification failed.
                            task.on_destroy()
        finally:
            sys.modules.pop(module_name, None)
            if added_path:
                sys.path.remove(str(path.parent))

    def _finished(self, run_id, owner, future):
        with self._lock:
            record = self._runs[run_id]['record']
            try:
                record['result'] = future.result()
                record['state'] = 'cancelled' if record['state'] == 'stopping' else 'succeeded'
            except (CancelledError, TaskDisabledException):
                record['state'] = 'cancelled'
            except BaseException as error:
                record['state'] = 'failed'
                record['error'] = f'{type(error).__name__}: {error}'[:2000]
                with Path(record['log_path']).open('a', encoding='utf-8') as output:
                    traceback.print_exception(type(error), error, error.__traceback__, file=output)
            finally:
                record['finished_at'] = time.time()
                try:
                    self._save(record)
                finally:
                    self.executor.release_exclusive(owner)
                    self._active = None
                    # Completed futures can retain traceback frames and whole task
                    # instances. Keep only the small serializable status record.
                    self._runs[run_id]['job'] = None

    def get_run_status(self, run_id: str):
        with self._lock:
            if run_id not in self._runs:
                raise ValueError(f'Unknown run_id: {run_id}')
            return dict(self._runs[run_id]['record'])

    def stop_task(self, run_id: str):
        """Request cancellation; stopping is not a terminal execution state."""
        with self._lock:
            status = self.get_run_status(run_id)
            if status['state'] not in TERMINAL_STATES:
                record = self._runs[run_id]['record']
                record['state'] = 'stopping'
                self._runs[run_id]['job'].cancel()
                self._save(record)
            return self.get_run_status(run_id)

    def screenshot(self):
        """Save a fresh idle capture, or the latest frame during execution."""
        job = None
        with self._lock:
            if self._closed:
                raise RuntimeError('MCP task runner is shutting down')
            if (self._active is None and self._observation_job is None and self.executor.current_job is None
                    and self.executor.current_task is None and self.executor.exclusive_owner is None):
                def capture():
                    if self.prepare is not None:
                        self.prepare()
                    self.executor._prepare_task_for_run(is_trigger_task=False)
                    if self.executor.next_frame(time_out=4) is None:
                        raise RuntimeError('Could not capture a fresh target frame')
                    return self.executor.get_frame_snapshot()

                job = self.executor.submit(capture, name='mcp:screenshot')
                self._observation_job = job
                job.future.add_done_callback(lambda _: self._observation_finished(job))
                cached = False
            else:
                cached = True
                snapshot = self.executor.get_frame_snapshot()
        if job is not None:
            # A bounded wait is just for this observation, never for a task run.
            try:
                snapshot = job.future.result(timeout=5)
            except TimeoutError:
                job.cancel()
                raise RuntimeError('Capture is still stopping; retry screenshot shortly') from None
        if snapshot is None:
            raise RuntimeError('No target frame is available yet; capture a frame in the task and retry')
        frame, captured_at = snapshot
        directory = self.artifact_directory / 'observations'
        directory.mkdir(parents=True, exist_ok=True)
        image = self.screenshot_service.to_pil_image(frame)
        path = directory / f'{uuid.uuid4().hex}.png'
        image.save(path)
        return {'path': str(path), 'captured_at': captured_at, 'cached': cached,
                'width': image.width, 'height': image.height}

    def _observation_finished(self, job):
        with self._lock:
            if self._observation_job is job:
                self._observation_job = None

    def close(self):
        with self._lock:
            self._closed = True
            if self._active is not None:
                self.stop_task(self._active)
            if self._observation_job is not None:
                self._observation_job.cancel()
