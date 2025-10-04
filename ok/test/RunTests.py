import unittest


# Define a test suite
def suite():
    loader = unittest.TestLoader()
    test_suite = loader.discover('tests')
    return test_suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner()
    runner.run(suite())

    from ok.test import ok

    ok.quit()
