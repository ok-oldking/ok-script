import unittest
from unittest.mock import patch

from ok.util import process


class TestProcessExecute(unittest.TestCase):
    def test_execute_uses_windows_start_command_by_default(self):
        game_path = r'C:\Games\Game.exe'

        with patch.object(process, 'get_path', return_value=game_path), \
                patch.object(process.os.path, 'exists', return_value=True), \
                patch.object(process.subprocess, 'Popen') as popen:
            self.assertTrue(process.execute(r'C:\Games\Game.exe -windowed', arguments='-dx11'))

        popen.assert_called_once()
        self.assertEqual(r'start "" /b "C:\Games\Game.exe" -windowed -dx11', popen.call_args.args[0])
        self.assertTrue(popen.call_args.kwargs['shell'])

    def test_execute_can_use_os_startfile_when_configured(self):
        game_path = r'C:\Games\Game.exe'

        with patch.object(process, 'get_path', return_value=game_path), \
                patch.object(process.os.path, 'exists', return_value=True), \
                patch.object(process.os, 'startfile', create=True) as startfile, \
                patch.object(process.subprocess, 'Popen') as popen:
            self.assertTrue(process.execute(
                r'C:\Games\Game.exe -windowed',
                arguments='-dx11',
                start_method=process.WINDOWS_START_METHOD_OS_STARTFILE,
            ))

        startfile.assert_called_once_with(game_path, 'open', '-windowed -dx11', r'C:\Games', 5)
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
