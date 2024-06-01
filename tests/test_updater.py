import unittest

from ok.logging.Logger import get_logger
from ok.update.Updater import Updater

logger = get_logger(__name__)


class TestUpdater(unittest.TestCase):

    def test_check_for_updates(self):
        logger.debug("start test_check_for_updates")
        # Create an Updater instance with a mocked config
        updater = Updater({'update': {'releases_url': 'https://api.github.com/repos/ok-oldking/ok-baijing/releases',
                                      'proxy_url': 'https://gh.ok-script.com'}})

        # Call the check_for_updates method
        releases = updater.check_for_updates()

        # Assert the function returned the expected result
        self.assertIsNotNone(releases)


if __name__ == '__main__':
    unittest.main()
