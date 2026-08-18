"""FastAPI/browser user interface adapter."""

from ok.ui.web.app import create_web_app
from ok.ui.web.server import run_web

__all__ = ["create_web_app", "run_web"]
