import unittest

from ok import Logger
from ok.gui.common.config import Language, cfg
from ok.test import init_ok, destroy_ok


class TaskTestCase(unittest.TestCase):
    task_class = None
    task = None
    config = None
    ok_map = {}
    logger = None
    lang = Language.CHINESE_SIMPLIFIED

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        cfg.language.value = cls.lang
        print(f'set language to {cls.lang} {cfg.language.value}')
        cls.config['trigger_tasks'] = []
        init_ok(cls.config)
        logger = Logger.get_logger(__name__)
        TaskTestCase.logger = logger
        logger.info(f'set up cls start {cls}')
        from ok import og
        cls.task = cls.task_class(og.executor)
        from ok.test import ok
        cls.task.feature_set = ok.feature_set
        cls.task.set_executor(ok.task_executor)

    @classmethod
    def tearDownClass(cls):
        destroy_ok()
        # if cls._ok is None:
        TaskTestCase.logger.info(f'tearDownClass cls {cls}')

    def set_image(self, image):
        from ok.test import ok
        ok.device_manager.capture_method.set_images([image])
        frame = self.task.next_frame()
        if self.task.executor.feature_set:
            self.task.executor.feature_set.check_size(frame)

    def set_images(self, *images):
        from ok.test import ok
        ok.device_manager.capture_method.set_images(images)
        self.task.next_frame()

    def tearDown(self):
        self.task.reset_scene()
