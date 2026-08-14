WEB_REQUIREMENTS_MESSAGE = (
    "The web UI requires FastAPI and Uvicorn. Install ok-script[web]."
)


def check_web_requirements():
    """Import required web packages before runtime workers are initialized."""
    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError as exc:
        raise SystemExit(WEB_REQUIREMENTS_MESSAGE) from exc
    return uvicorn
