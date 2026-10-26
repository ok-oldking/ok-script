import unittest
from unittest.mock import patch

import ok as ok_module
from ok import OK


class TestOKMutex(unittest.TestCase):
    def make_ok(self, config, mutex_result=True, args=None):
        with patch.object(ok_module, 'check_mutex') as check_mutex, \
                patch.object(OK, 'do_init', return_value=True), \
                patch.object(ok_module, 'config_logger'), \
                patch.object(ok_module, 'GlobalConfig'), \
                patch.object(ok_module.og, 'set_use_dml'), \
                patch.object(ok_module, 'parse_arguments_to_map', return_value=args or {}):
            check_mutex.return_value = mutex_result
            if mutex_result:
                OK(config)
            else:
                with self.assertRaisesRegex(RuntimeError, 'Another application instance'):
                    OK(config)
        return check_mutex

    def test_mutex_check_is_enabled_by_default(self):
        check_mutex = self.make_ok({})

        check_mutex.assert_called_once_with()

    def test_mutex_check_can_be_disabled_for_tests(self):
        check_mutex = self.make_ok({'check_mutex': False})

        check_mutex.assert_not_called()

    def test_gui_startup_requests_console_handoff(self):
        check_mutex = self.make_ok({'gui': {'type': 'qt'}})
        check_mutex.assert_called_once_with(gui=True)

    def test_headless_override_does_not_request_gui_handoff(self):
        check_mutex = self.make_ok({'gui': {'type': 'qt'}}, args={'headless': True})
        check_mutex.assert_called_once_with()

    def test_mutex_failure_stops_initialization(self):
        with patch('ok.core.plugin_staging.apply_pending_plugin_changes') as apply_changes:
            check_mutex = self.make_ok({}, mutex_result=False)
        check_mutex.assert_called_once_with()
        apply_changes.assert_not_called()

    def test_staged_changes_apply_after_mutex_before_runtime_initialization(self):
        order = []
        def checked():
            order.append('mutex')
            return True
        with patch.object(ok_module, 'check_mutex', side_effect=checked), \
                patch.object(OK, 'do_init', side_effect=lambda: order.append('initialize')), \
                patch('ok.core.plugin_staging.apply_pending_plugin_changes',
                      side_effect=lambda: order.append('apply') or {}), \
                patch.object(ok_module, 'config_logger'), \
                patch.object(ok_module, 'GlobalConfig'), \
                patch.object(ok_module.og, 'set_use_dml'), \
                patch.object(ok_module, 'parse_arguments_to_map', return_value={}):
            OK({})
        self.assertEqual(['mutex', 'apply', 'initialize'], order)


if __name__ == '__main__':
    unittest.main()
