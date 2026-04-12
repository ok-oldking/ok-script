"""IPC protocol for sandbox communication."""
import uuid


# --- Operation constants (Sandbox -> Main) ---

# Input operations
OP_CLICK = "click"
OP_MOUSE_DOWN = "mouse_down"
OP_MOUSE_UP = "mouse_up"
OP_SWIPE = "swipe"
OP_SCROLL = "scroll"
OP_SEND_KEY = "send_key"
OP_SEND_KEY_DOWN = "send_key_down"
OP_SEND_KEY_UP = "send_key_up"
OP_INPUT_TEXT = "input_text"
OP_MOVE = "move"
OP_BACK = "back"

# Capture operations
OP_GET_FRAME = "get_frame"
OP_GET_FRAME_SIZE = "get_frame_size"

# Feature operations
OP_FIND_FEATURE = "find_feature"
OP_GET_BOX_BY_NAME = "get_box_by_name"
OP_GET_FEATURE_BY_NAME = "get_feature_by_name"
OP_FEATURE_EXISTS = "feature_exists"

# OCR operations
OP_OCR = "ocr"

# Lifecycle operations
OP_SLEEP = "sleep"
OP_WAIT_CONDITION = "wait_condition"
OP_WAIT_SCENE = "wait_scene"
OP_RESET_SCENE = "reset_scene"
OP_NEXT_FRAME = "next_frame"

# Config operations
OP_GET_GLOBAL_CONFIG = "get_global_config"
OP_GET_CONFIG = "get_config"

# Device operations
OP_IS_ADB = "is_adb"
OP_IS_BROWSER = "is_browser"
OP_ENSURE_IN_FRONT = "ensure_in_front"
OP_ADB_SHELL = "adb_shell"
OP_ADB_UI_DUMP = "adb_ui_dump"

# Task operations
OP_GET_TASK_BY_CLASS = "get_task_by_class"
OP_RUN_TASK_BY_CLASS = "run_task_by_class"

# GUI operations (sandbox emits these to main)
OP_EMIT_DRAW_BOX = "emit_draw_box"
OP_EMIT_SCREENSHOT = "emit_screenshot"
OP_EMIT_NOTIFICATION = "emit_notification"
OP_EMIT_CLEAR_BOX = "emit_clear_box"

# Heartbeat
OP_PING = "ping"
OP_PONG = "pong"


# --- Host command constants (Main -> Sandbox) ---

CMD_RUN = "cmd_run"
CMD_TRIGGER = "cmd_trigger"
CMD_ENABLE = "cmd_enable"
CMD_DISABLE = "cmd_disable"
CMD_LOAD_SCRIPT = "cmd_load_script"
CMD_UNLOAD_SCRIPT = "cmd_unload_script"
CMD_SHUTDOWN = "cmd_shutdown"


class IPCMessage:
    """A single message in the sandbox IPC protocol."""

    def __init__(self, id, msg_type, op, kwargs=None, result=None, error=None):
        self.id = id
        self.type = msg_type
        self.op = op
        self.kwargs = kwargs or {}
        self.result = result
        self.error = error

    @classmethod
    def request(cls, op, **kwargs):
        return cls(
            id=str(uuid.uuid4()),
            msg_type="request",
            op=op,
            kwargs=kwargs,
        )

    @classmethod
    def response(cls, request_id, op, result=None, error=None):
        return cls(
            id=request_id,
            msg_type="response",
            op=op,
            result=result,
            error=error,
        )

    @classmethod
    def command(cls, op, **kwargs):
        return cls(
            id=str(uuid.uuid4()),
            msg_type="command",
            op=op,
            kwargs=kwargs,
        )

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "op": self.op,
            "kwargs": self.kwargs,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            msg_type=d["type"],
            op=d["op"],
            kwargs=d.get("kwargs"),
            result=d.get("result"),
            error=d.get("error"),
        )
