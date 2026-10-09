"""Exercise executor methods without a capture backend, GUI or game."""
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'ok/task/TaskExecutor.py'
CLASS = next(n for n in ast.parse(SOURCE.read_text(encoding='utf-8')).body
             if isinstance(n, ast.ClassDef) and n.name == 'TaskExecutor')


class Stopped(Exception):
    pass


def methods(names, env):
    selected = [n for n in CLASS.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env


class FrameIndependentTests(unittest.TestCase):
    def execute(self, frame_opt=None, trigger=False, fail=False):
        calls = []
        event = SimpleNamespace(value=False, is_set=lambda: event.value)
        def run():
            event.value = True
            calls.append('run')
            if fail:
                raise RuntimeError('expected')
        task = SimpleNamespace(name='test', run=run, disable=lambda: calls.append('disable'),
                               config={}, exit_after_task=False, info_set=lambda *a: None,
                               _app=SimpleNamespace(tr=lambda text: text))
        if frame_opt is not None:
            task.requires_initial_frame = frame_opt
        signal = SimpleNamespace(emit=lambda *a: calls.append('signal'))
        env = methods({'execute'}, {
            'logger': SimpleNamespace(info=lambda *a: None, debug=lambda *a: None, error=lambda *a: None),
            'communicate': SimpleNamespace(task=signal, task_done=signal, screenshot=signal, notification=signal),
            'time': time, 'prevent_sleeping': lambda flag: None, 'alert_info': lambda *a: None,
            'TaskDisabledException': Stopped, 'FinishedException': type('Finished', (Exception,), {}),
            'CaptureException': type('CaptureError', (Exception,), {}),
            'HotkeyConfigException': type('HotkeyError', (Exception,), {})})
        executor = SimpleNamespace(exit_event=event, paused=False, _last_frame_time=time.time(), _frame='cached',
            next_task=lambda: (task, True, trigger), reset_scene=lambda: None, _get_wake_version=lambda: 0,
            _prepare_task_for_run=lambda trigger: calls.append('prepare'),
            next_frame=lambda **kw: calls.append('frame') or 'image', destroy=lambda: calls.append('destroy'))
        # A missing .frame property deliberately catches accidental capture on error.
        with patch.dict('sys.modules', {'ok': SimpleNamespace(og=SimpleNamespace())}):
            env['execute'](executor)
        return calls

    def test_opt_in_skips_frame_and_input_preparation(self):
        calls = self.execute(False)
        self.assertIn('run', calls)
        self.assertNotIn('frame', calls)
        self.assertNotIn('prepare', calls)

    def test_ordinary_task_preserves_frame_guard(self):
        calls = self.execute()
        self.assertIn('frame', calls)
        self.assertIn('prepare', calls)

    def test_trigger_cannot_opt_out_of_frame_guard(self):
        self.assertIn('frame', self.execute(False, trigger=True))

    def test_control_error_uses_cached_frame(self):
        calls = self.execute(False, fail=True)
        self.assertIn('disable', calls)
        self.assertIn('destroy', calls)
        self.assertNotIn('frame', calls)

    def idle(self):
        env = methods({'_has_pending_frame_independent_task', 'next_frame', 'sleep'}, {'time': time})
        trigger = SimpleNamespace(enabled=True)
        queued = SimpleNamespace(enabled=True, requires_initial_frame=False)
        executor = SimpleNamespace(current_task=trigger, trigger_tasks=[trigger], onetime_task_queue=[queued],
            reset_scene=lambda **kw: None, check_enabled=lambda **kw: None, debug_mode=False,
            exit_event=SimpleNamespace(is_set=lambda: False))
        executor._has_pending_frame_independent_task = lambda: env['_has_pending_frame_independent_task'](executor)
        return executor, queued, env

    def test_idle_trigger_yields_sleep_and_frame(self):
        executor, _, env = self.idle()
        self.assertTrue(executor._has_pending_frame_independent_task())
        env['sleep'](executor, 1)
        self.assertIsNone(env['next_frame'](executor))

    def test_pending_control_never_preempts_business_task(self):
        executor, _, _ = self.idle()
        executor.current_task = SimpleNamespace()
        self.assertFalse(executor._has_pending_frame_independent_task())
        executor.current_task = None
        self.assertTrue(executor._has_pending_frame_independent_task())

    def test_disabled_or_ordinary_queue_does_not_preempt(self):
        executor, queued, _ = self.idle()
        queued.enabled = False
        self.assertFalse(executor._has_pending_frame_independent_task())
        queued.enabled = True
        queued.requires_initial_frame = True
        self.assertFalse(executor._has_pending_frame_independent_task())


if __name__ == '__main__':
    unittest.main()
