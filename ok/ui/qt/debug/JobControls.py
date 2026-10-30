import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import PrimaryPushButton, PushButton, CaptionLabel, FluentIcon

from ok import og
from ok import Logger
from ok.core.code_runner import wait_result
from ok.task.exceptions import ExecutorBusyException
from ok.ui.qt.util.Alert import alert_error

logger = Logger.get_logger(__name__)


class JobControls(QWidget):
    """Run and Stop buttons plus status for one executor job at a time.

    While the job waits behind a running one-time task, it offers to stop that
    task. ``output`` and ``finished`` are delivered on the GUI thread.
    """
    run_clicked = Signal()
    output = Signal(str)
    finished = Signal(object)
    _done = Signal(object)

    def __init__(self, run_text, parent=None):
        super().__init__(parent)
        self.job = None
        self._start_time = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.run_button = PrimaryPushButton(FluentIcon.PLAY, run_text, self)
        self.run_button.clicked.connect(self.run_clicked)
        layout.addWidget(self.run_button)

        self.stop_button = PushButton(FluentIcon.CLOSE, self.tr('Stop'), self)
        self.stop_button.clicked.connect(self.stop)
        layout.addWidget(self.stop_button)

        self.stop_task_button = PushButton(self.tr('Stop Current Task'), self)
        self.stop_task_button.clicked.connect(self.stop_current_task)
        layout.addWidget(self.stop_task_button)

        self.status_label = CaptionLabel(self)
        layout.addWidget(self.status_label, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._update_status)
        self._done.connect(self._on_done)
        self._set_running(False)

    def start(self, submit):
        """Start ``submit(on_output)``, which returns a job from ok.core.code_runner.

        Returns the job, or None if it could not be submitted.
        """
        if self.job is not None:
            return None
        try:
            job = submit(self.output.emit)
        except ExecutorBusyException as e:
            alert_error(self.tr('The app is controlled by {owner}').format(owner=e.owner))
            return None
        except Exception as e:
            logger.error('submit job failed', e)
            alert_error(str(e))
            return None
        self.job = job
        self._start_time = time.time()
        self._set_running(True)
        self._timer.start()
        self._update_status()
        job.future.add_done_callback(lambda _: self._done.emit(job))
        return job

    def stop(self):
        if self.job is not None:
            self.job.cancel()
            self.status_label.setText(self.tr('Stopping...'))

    def stop_current_task(self):
        task = og.executor.current_task
        if task is not None and task in og.executor.onetime_tasks:
            logger.info(f'stop {task} for debug job')
            task.disable()

    def _on_done(self, job):
        if job is not self.job:
            return
        self.job = None
        self._timer.stop()
        self._set_running(False)
        result = wait_result(job)
        if result.cancelled:
            self.status_label.setText(self.tr('Cancelled'))
        elif result.error:
            self.status_label.setText(self.tr('Failed after {seconds}s').format(seconds=f'{result.duration:.2f}'))
        else:
            self.status_label.setText(self.tr('Done in {seconds}s').format(seconds=f'{result.duration:.2f}'))
        self.finished.emit(result)

    def _update_status(self):
        job = self.job
        if job is None:
            return
        if job.cancel_requested:
            return
        if job.future.running():
            self.stop_task_button.hide()
            seconds = f'{time.time() - self._start_time:.1f}'
            self.status_label.setText(self.tr('Running {seconds}s').format(seconds=seconds))
            return
        current = og.executor.current_task
        if current is not None:
            self.status_label.setText(self.tr('Waiting for {task}').format(task=og.app.tr(current.name)))
            self.stop_task_button.setVisible(current in og.executor.onetime_tasks)
        else:
            self.stop_task_button.hide()
            self.status_label.setText(self.tr('Waiting for the executor...'))

    def _set_running(self, running):
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if not running:
            self.stop_task_button.hide()
