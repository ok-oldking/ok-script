import unittest
from unittest.mock import patch

import ok as ok_module
from ok import OK


class TestOKMutex(unittest.TestCase):
    def make_ok(self, config):
        with patch.object(ok_module, 'check_mutex') as check_mutex, \
                patch.object(OK, 'do_init', return_value=True), \
                patch.object(ok_module, 'config_logger'), \
                patch.object(ok_module, 'GlobalConfig'), \
                patch.object(ok_module.og, 'set_use_dml'), \
                patch.object(ok_module, 'parse_arguments_to_map', return_value={}):
            OK(config)
        return check_mutex

    def test_mutex_check_is_enabled_by_default(self):
        check_mutex = self.make_ok({})

        check_mutex.assert_called_once_with()

    def test_mutex_check_can_be_disabled_for_tests(self):
        check_mutex = self.make_ok({'check_mutex': False})

        check_mutex.assert_not_called()


if __name__ == '__main__':
    unittest.main()
