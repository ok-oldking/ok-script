import unittest
from unittest.mock import patch

import ok.cli as cli


class TestCli(unittest.TestCase):
    def test_parser_exposes_all_runtime_modes(self):
        parser = cli.build_parser()

        self.assertEqual("gui", parser.parse_args(["gui"]).command)
        self.assertEqual("run_task", parser.parse_args(["run_task", "DailyTask"]).command)
        with self.assertRaises(SystemExit):
            parser.parse_args(["web"])

    def test_gui_command_uses_nested_qt_config(self):
        config = {"gui_title": "Test"}

        with patch.object(cli, "load_config", return_value=config), \
                patch("ok.OK") as ok_class:
            self.assertEqual(0, cli.main(["gui"]))

        ok_class.assert_called_once_with({
            "gui_title": "Test", "gui": {"type": "qt"},
        })
        ok_class.return_value.start.assert_called_once_with()

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
