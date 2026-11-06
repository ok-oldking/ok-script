"""Start the ok-script GUI from this checkout with a demo config, for manual UI testing.

    .venv\\Scripts\\python.exe main.py

Targets Notepad, so no game is needed. Settings and logs go to the git-ignored
``configs/`` and ``logs/`` folders of the working directory.
"""

from ok import OK
from ok.task.task import BaseTask, TriggerTask


class DemoTask(BaseTask):
    """A one-time task with a few config types, so the Tasks page has content."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Demo Task'
        self.description = 'Logs a message a few times'
        self.support_schedule_task = True
        self.default_config.update({
            'Repeat': 3,
            'Message': 'Hello from ok-script',
            'Verbose': False,
            'Mode': 'Fast',
        })
        self.config_type['Mode'] = {'type': 'drop_down', 'options': ['Fast', 'Slow']}
        self.config_description['Repeat'] = 'How many times to log the message'

    def run(self):
        for i in range(self.config.get('Repeat')):
            self.log_info(f"{self.config.get('Message')} ({i + 1})", notify=i == 0)
            self.sleep(1 if self.config.get('Mode') == 'Fast' else 3)


class DemoTrigger(TriggerTask):
    """A trigger task that only logs, so the trigger list is not empty."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Demo Trigger'
        self.description = 'Logs once every 10 seconds while enabled'
        self.trigger_interval = 10

    def run(self):
        self.log_info('demo trigger fired')


config = {
    'gui_title': 'ok-script dev',
    'version': 'dev',
    'debug': True,  # shows the Templates page and debug tools
    'gui': {'type': 'qt'},
    'windows': {
        'exe': 'notepad.exe',
        'capture_method': ['WGC', 'BitBlt_RenderFull'],
    },
    'onetime_tasks': [[__name__, 'DemoTask']],
    'trigger_tasks': [[__name__, 'DemoTrigger']],
}

if __name__ == '__main__':
    OK(config).start()
