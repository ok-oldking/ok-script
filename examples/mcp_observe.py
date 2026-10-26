"""A read-only task file for checking the MCP development workflow.

Pass this file's absolute path to run_task. The project must already have a
configured capture target. Replace these methods with application-specific
recovery, starting-state checks and automation when developing a real task.
"""

import json

from ok import BaseTask


class Task(BaseTask):
    def reset_to_start(self):
        # This observation task changes no application state, so recovery is
        # a no-op. A task that clicks or types must restore its own baseline.
        self.log_info('Preparing an observation of the configured target')

    def verify_start_state(self):
        frame = self.executor.next_frame(time_out=4)
        assert frame is not None and frame.size > 0, 'Target UI is unavailable'

    def run(self):
        self.screenshot('mcp_observe')
        height, width = self.frame.shape[:2]
        observation = {'width': width, 'height': height}
        (self.artifact_directory / 'observation.json').write_text(
            json.dumps(observation, indent=2), encoding='utf-8')
        self.log_info(f'Observed target UI: {width}x{height}')
        assert width > 0 and height > 0
