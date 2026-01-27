import sys
import threading
import time

from PySide6.QtCore import QCoreApplication

from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_info
from ok.task.exceptions import FinishedException, TaskDisabledException, WaitFailedException, CaptureException
from ok.util.GlobalConfig import basic_options
from ok.util.logger import Logger, config_logger
from ok.util.process import is_cuda_12_or_above, prevent_sleeping
from ok.util.window import ratio_text_to_number

logger = Logger.get_logger(__name__)

cdef class TaskExecutor:
    cdef public object _frame
    cdef public bint paused
    cdef double pause_start
    cdef double pause_end_time
    cdef double _last_frame_time
    cdef double wait_until_timeout
    cdef public object device_manager
    cdef public object feature_set
    cdef double wait_until_settle_time
    cdef double wait_scene_timeout
    cdef public object exit_event
    cdef public bint debug_mode
    cdef public bint debug
    cdef public object global_config
    cdef public dict _ocr_lib
    cdef public int ocr_target_height
    cdef public object current_task
    cdef str config_folder
    cdef int trigger_task_index
    cdef public list trigger_tasks
    cdef public list onetime_tasks
    cdef object thread, locale
    cdef public object scene
    cdef public dict text_fix
    cdef public object ocr_po_translation
    cdef public object config, basic_options
    cdef object lock

    def __init__(self, device_manager,
                 wait_until_timeout=10, wait_until_settle_time=-1,
                 exit_event=None, feature_set=None,
                 ocr_lib=None,
                 config_folder=None, debug=False, global_config=None, ocr_target_height=0, config=None):
        self._frame = None
        device_manager.executor = self
        self.pause_start = time.time()
        self.pause_end_time = time.time()
        self._last_frame_time = 0
        self.paused = True
        self.config = config
        self.scene = None
        from ok.gui.common.config import cfg
        self.locale = cfg.get(cfg.language).value
        self.text_fix = {}
        self.ocr_po_translation = None
        self.load_tr()
        self.ocr_target_height = ocr_target_height
        self.device_manager = device_manager
        self.feature_set = feature_set
        self.wait_until_settle_time = wait_until_settle_time
        self.wait_scene_timeout = wait_until_timeout
        self.exit_event = exit_event
        self.debug_mode = False
        self.debug = debug
        self.global_config = global_config
        self._ocr_lib = {}
        if self.config.get('ocr') and not self.config.get('ocr').get('default', False):
            self.config['ocr']['default'] = self.config.get('ocr')
        self.current_task = None
        self.config_folder = config_folder or "config"
        self.trigger_task_index = -1
        self.basic_options = global_config.get_config(basic_options)

        self.trigger_tasks = []
        self.onetime_tasks = []
        self.thread = None
        self.lock = threading.Lock()

    cdef load_tr(self):
        locale_name = self.locale.name()
        try:
            from ok.gui.i18n.GettextTranslator import get_ocr_translations
            self.ocr_po_translation = get_ocr_translations(locale_name)
            self.ocr_po_translation.install()
            logger.info(f'translation ocr installed for {locale_name}')
        except:
            logger.error(f'install ocr translations error for {locale_name}')
            self.ocr_po_translation = None

    @property
    def interaction(self):
        return self.device_manager.interaction

    @property
    def method(self):
        return self.device_manager.capture_method

    def ocr_lib(self, name="default"):
        if name not in self._ocr_lib:
            lib = self.config.get('ocr').get(name).get('lib')
            to_download = self.config.get('ocr').get(name).get('download_models')
            if to_download:
                models = self.config.get('download_models').get(to_download)
                from ok.gui.util.download import download_models
                download_models(models)

            config_params = self.config.get('ocr').get(name).get('params')
            if config_params is None:
                config_params = {}
            if lib == 'paddleocr':
                logger.info('use paddleocr as ocr lib')
                from paddleocr import PaddleOCR
                lang = 'ch'
                config_params['use_textline_orientation'] = False
                config_params['use_doc_unwarping'] = False
                config_params['use_doc_orientation_classify'] = False
                config_params['device'] = "gpu" if is_cuda_12_or_above() else "cpu"
                logger.info(f'init PaddleOCR with {config_params}')
                self._ocr_lib[name] = PaddleOCR(**config_params)
                import logging
                logging.getLogger('ppocr').setLevel(logging.ERROR)
                config_logger(self.config)
            elif lib == 'dgocr':
                if config_params.get('use_dml', True):
                    config_params['use_dml'] = True
                from dgocr import DGOCR
                self._ocr_lib[name] = DGOCR(**config_params)
            elif lib == 'onnxocr':
                from onnxocr.onnx_paddleocr import ONNXPaddleOcr
                logger.info(f'init onnxocr {config_params}')
                self._ocr_lib[name] = ONNXPaddleOcr(use_angle_cls=False, use_gpu=False, use_dml=False,
                                                    use_openvino=config_params.get('use_openvino', False))
            elif lib == 'rapidocr':
                from rapidocr import RapidOCR
                params = {"Global.use_cls": False, "Global.max_side_len": 100000, "Global.min_side_len": 0,
                          "EngineConfig.onnxruntime.use_dml": False}
                params.update(config_params)
                logger.info(f'init rapidocr {params}')
                self._ocr_lib[name] = RapidOCR(params=params)
            else:
                raise Exception(f'ocr lib not supported: {lib}')
            logger.info(f'ocr_lib init {self._ocr_lib[name]} {lib}')
        return self._ocr_lib[name]

    def nullable_frame(self):
        return self._frame

    def check_frame_and_resolution(self, supported_ratio, min_size, time_out=8.0):
        if supported_ratio is None or min_size is None:
            return True, '0x0'
        logger.info(f'start check_frame_and_resolution')
        self.device_manager.update_resolution_for_hwnd()
        cdef double start = time.time()
        cdef object frame = None
        while frame is None and (time.time() - start) < time_out:
            frame = self.method.get_frame()
            time.sleep(0.1)
        if frame is None:
            logger.error(f'check_frame_and_resolution failed can not get frame after {time_out} {time.time() - start}')
            return False, '0x0'
        cdef int width = self.method.width
        cdef int height = self.method.height
        cdef actual_ratio = 0
        if height == 0:
            actual_ratio = 0
        else:
            actual_ratio = width / height
        supported_ratio = ratio_text_to_number(supported_ratio)
        # Calculate the difference between the actual and supported ratios
        difference = abs(actual_ratio - supported_ratio)
        support = difference <= 0.01 * supported_ratio
        if not support:
            logger.error(f'resolution error {width}x{height} {frame is None}')
        if not support and frame is not None:
            communicate.screenshot.emit(frame, "resolution_error", False, None)
        # Check if the difference is within 1%
        if support and min_size is not None:
            if width < min_size[0] or height < min_size[1]:
                support = False
        return support, f"{width}x{height}"

    def can_capture(self):
        return self.method is not None and self.interaction is not None and self.interaction.should_capture()

    def next_frame(self):
        self.reset_scene()
        while not self.exit_event.is_set():
            if self.can_capture():
                frame = self.method.get_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    if height <= 0 or width <= 0:
                        logger.warning(f"captured wrong size frame: {width}x{height}")
                    self._frame = frame
                    self._last_frame_time = time.time()
                    return self._frame
            self.sleep(1)
            logger.error("got no frame!")
        raise FinishedException()

    def is_executor_thread(self):
        return self.thread == threading.current_thread()

    def connected(self):
        return self.method is not None and self.method.connected()

    @property
    def frame(self):
        while self.paused and not self.debug_mode:
            self.sleep(1)
        if self.exit_event.is_set():
            logger.info("frame Exit event set. Exiting early.")
            sys.exit(0)
        if self._frame is None:
            self.next_frame()
        return self._frame

    cpdef check_enabled(self, check_pause=True):
        if check_pause and self.paused:
            self.sleep(1)
        if self.current_task and not self.current_task.enabled:
            logger.info(f'{self.current_task} is disabled, raise Exception')
            self.current_task = None
            raise TaskDisabledException()

    cpdef sleep(self, double timeout):
        """
        Sleeps for the specified timeout, checking for an exit event every 100ms, with adjustments to prevent oversleeping.

        :param timeout: The total time to sleep in seconds.
        """
        if timeout <= 0:
            return
        self.reset_scene(check_enabled=False)
        if self.debug_mode:
            time.sleep(timeout)
            return
        self.pause_end_time = time.time() + timeout
        cdef double to_sleep = 0
        cdef object task
        while True:
            self.check_enabled(check_pause=False)
            if self.current_task is not None:
                task = self.current_task
                if task.sleep_check_interval >= 0:
                    if not task.in_sleep_check and time.time() - task.last_sleep_check_time > task.sleep_check_interval:
                        task.last_sleep_check_time = time.time()
                        task.in_sleep_check = True
                        try:
                            self.next_frame()
                            task.sleep_check()
                            self.reset_scene()
                        except Exception as e:
                            logger.error(f"sleep_check error {task}", e)
                            raise
                        finally:
                            task.in_sleep_check = False
            if self.exit_event.is_set():
                logger.info("sleep Exit event set. Exiting early.")
                sys.exit(0)
            if not (self.paused or (
                    self.current_task is not None and self.current_task.paused) or self.interaction is None or not self.interaction.should_capture()):
                to_sleep = self.pause_end_time - time.time()
                if to_sleep <= 0:
                    return
                if to_sleep > 0.01:
                    to_sleep = 0.01
                time.sleep(to_sleep)
            else:
                time.sleep(0.1)

    def pause(self, task=None):
        if task is not None:
            if self.current_task != task:
                raise Exception(f"Can only pause current task {self.current_task}")
        elif not self.paused:
            self.paused = True
            communicate.executor_paused.emit(self.paused)
            self.reset_scene(check_enabled=False)
            self.pause_start = time.time()
            return True

    def stop_current_task(self):
        if task := self.current_task:
            task.disable()
            task.unpause()

    def start(self):
        with self.lock:
            if self.thread is None:
                self.thread = threading.Thread(target=self.execute, name="TaskExecutor")
                self.thread.start()
            if self.paused:
                self.paused = False
                communicate.executor_paused.emit(self.paused)
                self.pause_end_time += self.pause_start - time.time()

    def wait_condition(self, condition, time_out=0, pre_action=None, post_action=None, settle_time=-1,
                       raise_if_not_found=False):
        self.reset_scene()
        start = time.time()
        if time_out == 0:
            time_out = self.wait_scene_timeout
        settled = 0
        result = None
        while not self.exit_event.is_set():
            if pre_action is not None:
                pre_action()
            self.next_frame()
            result = condition()
            result_str = list_or_obj_to_str(result)
            if result:
                logger.debug(
                    f"found result {result_str} {(time.time() - start):.3f}")
                if settle_time == -1:
                    settle_time = self.wait_until_settle_time
                if settle_time > 0:
                    if settled > 0 and time.time() - settled > settle_time:
                        return result
                    if settled == 0:
                        settled = time.time()
                    continue
                else:
                    return result
            else:
                settled = 0
            if post_action is not None:
                post_action()
            if time.time() - start > time_out:
                logger.info(f"wait_until timeout {condition} {time_out} seconds")
                break
        if raise_if_not_found:
            raise WaitFailedException()
        return None

    def reset_scene(self, check_enabled=True):
        if check_enabled:
            self.check_enabled()
        self._frame = None
        if self.scene:
            self.scene.reset()

    cdef tuple next_task(self):
        if self.exit_event.is_set():
            logger.error(f"next_task exit_event.is_set exit")
            return None, False, False
        for onetime_task in self.onetime_tasks:
            if onetime_task.enabled:
                logger.info(f'get one enabled onetime_task {onetime_task.name}')
                return onetime_task, True, False
        cycled = False
        for _ in range(len(self.trigger_tasks)):
            if self.trigger_task_index == len(self.trigger_tasks) - 1:
                self.trigger_task_index = -1
                self.trigger_sleep()
                cycled = True
            self.trigger_task_index += 1
            task = self.trigger_tasks[self.trigger_task_index]
            if task.enabled and task.should_trigger():
                return task, cycled, True
        return None, cycled, False

    def active_trigger_task_count(self):
        return len([x for x in self.trigger_tasks if x.enabled])

    cdef trigger_sleep(self):
        if interval := self.basic_options.get('Trigger Interval', 1):
            self.sleep(interval / 1000)

    cdef execute(self):
        logger.info(f"start execute")
        cdef object task
        cdef bint cycled
        while not self.exit_event.is_set():
            if self.paused:
                logger.info(f'executor is paused sleep')
                self.sleep(1)
            task, cycled, is_trigger_task = self.next_task()
            if not task:
                time.sleep(1)
                continue
            if cycled:
                self.reset_scene()
            elif time.time() - self._last_frame_time > 0.2:
                self.reset_scene()
            try:
                task.start_time = time.time()
                if not is_trigger_task:
                    task.running = True
                    self.current_task = task
                    communicate.task.emit(task)
                if cycled or self._frame is None:
                    self.next_frame()
                if is_trigger_task:
                    if task.run():
                        self.trigger_task_index = -1
                        self.reset_scene()
                        continue
                else:
                    prevent_sleeping(True)
                    logger.debug(f'start running onetime_task {task.name}')
                    task.run()
                    logger.debug(f'end running onetime_task {task.name}')
                    prevent_sleeping(False)
                    task.disable()
                    communicate.task_done.emit(task)
                    if task.exit_after_task or task.config.get('Exit After Task'):
                        logger.info('Successfully Executed Task, Exiting Game and App!')
                        alert_info('Successfully Executed Task, Exiting Game and App!')
                        time.sleep(5)
                        self.device_manager.stop_hwnd()
                        time.sleep(5)
                        communicate.quit.emit()
                self.current_task = None
                if not is_trigger_task:
                    communicate.task.emit(task)
                if self.current_task is not None:
                    self.current_task.running = False
                    if not is_trigger_task:
                        communicate.task.emit(self.current_task)
                    self.current_task = None
            except TaskDisabledException:
                logger.info(f"TaskDisabledException, continue {task}")
                from ok import og
                communicate.notification.emit('Stopped', task.name, False,
                                              True, "start")
                continue
            except FinishedException:
                logger.info(f"FinishedException, breaking")
                break
            except Exception as e:
                if isinstance(e, CaptureException):
                    communicate.capture_error.emit()
                name = task.name
                task.disable()
                from ok import og
                error = str(e)
                communicate.notification.emit(error, name, True, True, None)
                tab = "trigger" if is_trigger_task else "onetime"
                task.info_set(QCoreApplication.tr('app', 'Error'), error)
                logger.error(f"{name} exception", e)
                if self._frame is not None:
                    communicate.screenshot.emit(self.frame, name, True, None)
                self.current_task = None
                communicate.task.emit(None)
        self.destory()

    def stop(self):
        logger.info('stop')
        self.exit_event.set()

    def destory(self):
        logger.info(f'Executor destory')
        for task in self.onetime_tasks:
            task.on_destroy()
        self.onetime_tasks = []
        for task in self.trigger_tasks:
            task.on_destroy()
        self.trigger_tasks = []
        if self.interaction:
            self.interaction.on_destroy()
        if self.method:
            self.method.close()

    def wait_until_done(self):
        self.thread.join()

    def get_all_tasks(self):
        return self.onetime_tasks + self.trigger_tasks

    def get_task_by_class_name(self, class_name):
        for onetime_task in self.onetime_tasks:
            if onetime_task.__class__.__name__ == class_name:
                return onetime_task
        for trigger_task in self.trigger_tasks:
            if trigger_task.__class__.__name__ == class_name:
                return trigger_task

    def get_task_by_class(self, cls):
        logger.debug(f'get_task_by_class {cls} {self.onetime_tasks} {self.trigger_tasks}')
        for onetime_task in self.onetime_tasks:
            if isinstance(onetime_task, cls):
                return onetime_task
        for trigger_task in self.trigger_tasks:
            if isinstance(trigger_task, cls):
                return trigger_task

def list_or_obj_to_str(val):
    if val is not None:
        if isinstance(val, list):
            return ', '.join(str(obj) for obj in val)
        else:
            return str(val)
    else:
        return None
