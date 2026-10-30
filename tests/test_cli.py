import unittest
from unittest.mock import patch

import ok.cli as cli


class TestCli(unittest.TestCase):
    def test_parser_exposes_all_runtime_modes(self):
        parser = cli.build_parser()

        self.assertEqual("gui", parser.parse_args(["gui"]).command)
        self.assertEqual("run_task", parser.parse_args(["run_task", "DailyTask"]).command)
        self.assertEqual("mcp", parser.parse_args(["mcp"]).command)
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

    def test_mcp_command_starts_headless_runtime_and_cleans_up(self):
        config = {'gui': {'type': 'qt'}, 'mcp': {'artifact_directory': 'logs/dev'}}
        with patch.object(cli, 'load_config', return_value=config), patch('ok.OK') as ok_class:
            self.assertEqual(0, cli.main(['mcp', '--port', '8766']))
        ok_class.assert_called_once_with({
            'gui': None, 'mcp': {'artifact_directory': 'logs/dev', 'enabled': True, 'port': 8766}})
        runtime = ok_class.return_value
        runtime.start_mcp_server.assert_called_once_with()
        runtime.start.assert_called_once_with()
        runtime.quit.assert_called_once_with()
        self.assertEqual({'type': 'qt'}, config['gui'])

    def test_gui_can_enable_mcp(self):
        with patch.object(cli, 'load_config', return_value={}), patch('ok.OK') as ok_class:
            self.assertEqual(0, cli.main(['gui', '--mcp', '--mcp-port', '8767']))
        ok_class.assert_called_once_with({
            'gui': {'type': 'qt'}, 'mcp': {'enabled': True, 'port': 8767}})

    def test_mcp_modes_preserve_configured_port_unless_explicitly_overridden(self):
        for command, flag in [('mcp', '--port'), ('gui', '--mcp-port')]:
            for override in [None, 0, 8767]:
                with self.subTest(command=command, override=override):
                    config = {'mcp': {'port': 9000, 'enabled': False}}
                    arguments = [command] + (['--mcp'] if command == 'gui' else [])
                    if override is not None:
                        arguments += [flag, str(override)]
                    with patch.object(cli, 'load_config', return_value=config), patch('ok.OK') as ok_class:
                        self.assertEqual(0, cli.main(arguments))
                    self.assertEqual(ok_class.call_args.args[0]['mcp'], {
                        'enabled': True, 'port': 9000 if override is None else override})
                    self.assertEqual(config['mcp'], {'port': 9000, 'enabled': False})


if __name__ == "__main__":
    unittest.main()
