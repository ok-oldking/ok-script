from ok import ImageCaptureMethod
from ok import DoNothingInteraction

ok = None


def init_ok(config):
    global ok
    if ok is None:
        from ok import OK
        config['debug'] = True
        config['analytics'] = None
        ok = OK(config)
        ok.task_executor.debug_mode = True
        ok.device_manager.capture_method = ImageCaptureMethod(
            ok.device_manager.exit_event, [])
        ok.device_manager.interaction = DoNothingInteraction(
            ok.device_manager.capture_method)
        ok.app
        ok.task_executor.start()


def destroy_ok():
    global ok
    if ok is not None:
        ok.quit()
