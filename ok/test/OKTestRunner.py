import unittest

from ok.test import ok


class OKTestResult(unittest.TestResult):
    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super().__init__(stream, descriptions, verbosity)

    def startTestRun(self):
        super().startTestRun()
        print("Before all tests run!")

    def stopTestRun(self):
        super().stopTestRun()
        ok.quit()

        print("All unit tests are done!")


class OKTestRunner(unittest.TextTestRunner):
    def _makeResult(self):
        return OKTestResult(self.stream, self.descriptions, self.verbosity)
