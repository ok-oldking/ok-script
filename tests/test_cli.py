import unittest
from unittest.mock import patch

import ok.cli as cli


class TestCli(unittest.TestCase):
    def test_run_task_forwards_exit_after_flag(self):
        config = {"use_gui": False}

        with patch.object(cli, "load_config", return_value=config), \
                patch("ok.run_task", return_value=True) as run_task:
            self.assertEqual(0, cli.main(["run_task", "DailyTask", "-e"]))

        run_task.assert_called_once_with(config, task="DailyTask", debug=False, exit_after=True)

    def test_run_task_defaults_exit_after_to_false(self):
        config = {"use_gui": False}

        with patch.object(cli, "load_config", return_value=config), \
                patch("ok.run_task", return_value=True) as run_task:
            self.assertEqual(0, cli.main(["run_task", "DailyTask"]))

        run_task.assert_called_once_with(config, task="DailyTask", debug=False, exit_after=False)


if __name__ == "__main__":
    unittest.main()
