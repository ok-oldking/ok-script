import unittest
from unittest.mock import patch

import ok.cli as cli


class TestCli(unittest.TestCase):
    def test_parser_exposes_all_runtime_modes(self):
        parser = cli.build_parser()

        self.assertEqual("gui", parser.parse_args(["gui"]).command)
        web = parser.parse_args(["web", "--host", "0.0.0.0", "--port", "9000"])
        self.assertEqual(("web", "0.0.0.0", 9000), (web.command, web.host, web.port))
        self.assertEqual(0, parser.parse_args(["web"]).port)

    def test_web_command_uses_shared_launcher(self):
        config = {"use_gui": True}

        with patch.object(cli, "load_config", return_value=config), \
                patch("ok.run_web") as run_web:
            self.assertEqual(0, cli.main(["web", "--host", "localhost"]))

        run_web.assert_called_once_with(
            config, host="localhost", port=0, open_browser=False
        )

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
