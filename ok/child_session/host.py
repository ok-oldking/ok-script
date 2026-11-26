"""Host-side setup for the child session: agent autostart and the agent's settings file."""

import os
import sys
import winreg

from ok.child_session import protocol
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
DEFAULT_RESOLUTION = (1920, 1080)
# Common startup apps that only waste memory in the child session, or sign in twice.
DEFAULT_CLOSE_APPS = ['QQ.exe', 'QQMusic.exe', 'WeChat.exe', 'Weixin.exe', 'OneDrive.exe', 'Discord.exe',
                      'Telegram.exe']


def project_dir() -> str:
    return os.path.abspath(os.getcwd())


_settings = None


def settings():
    """The user's child-session settings (``configs/child_session.json``)."""
    global _settings
    if _settings is None:
        from ok.util.config import Config
        _settings = Config('child_session', {
            'close_apps': list(DEFAULT_CLOSE_APPS),
            'elevate': True,
            'view_only': True,
            'auto_connect': True,
        })
    return _settings


def sync_agent_config(windows_config: dict) -> dict:
    """Write the agent's settings file from the app config and the user's settings."""
    current = settings()
    return write_agent_config(project_dir(), windows_config, current.get('close_apps'), current.get('elevate', True))


def _pythonw() -> str:
    executable = sys.executable
    folder, name = os.path.split(executable)
    if name.lower() == 'python.exe':
        candidate = os.path.join(folder, 'pythonw.exe')
        if os.path.exists(candidate):
            return candidate
    return executable


def agent_script() -> str:
    # Resolved: a project may reach ok-script through a symbolic link, and the startup
    # list in the child session did not launch the agent through one.
    return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.py'))


def autostart_name(project: str) -> str:
    return f'ok-script-child-session-{protocol.project_key(project)}'


def autostart_arguments(project: str) -> str:
    return f'"{agent_script()}" --project "{project}"'


def autostart_command(project: str) -> str:
    return f'"{_pythonw()}" {autostart_arguments(project)}'


# The agent starts from a shortcut in the user's Startup folder. A registry Run entry
# was tried first, but on a tested PC it was removed around child-session sign-ins,
# while Startup-folder shortcuts kept working.

def startup_folder() -> str:
    from win32com.shell import shell, shellcon
    return shell.SHGetFolderPath(0, shellcon.CSIDL_STARTUP, None, 0)


def shortcut_path(project: str) -> str:
    return os.path.join(startup_folder(), f'{autostart_name(project)}.lnk')


def _wscript_shell():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()  # status refresh runs on a worker thread
    return win32com.client.Dispatch('WScript.Shell')


def autostart_value(project: str):
    """The installed shortcut's command line, or None when there is none."""
    path = shortcut_path(project)
    if not os.path.exists(path):
        return None
    try:
        link = _wscript_shell().CreateShortcut(path)
        return f'"{link.TargetPath}" {link.Arguments}'
    except Exception as e:
        logger.error(f'cannot read {path}', e)
        return ''


def is_autostart_installed(project: str) -> bool:
    """True when the shortcut exists and starts this version's agent for this project."""
    return autostart_value(project) == autostart_command(project)


def _remove_legacy_run_entry(project: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, autostart_name(project))
        logger.info('removed the old registry startup entry of the child session agent')
    except OSError:
        pass


def install_autostart(project: str) -> None:
    """Start the agent at every sign-in; it exits at once outside a child session.

    Always rewrites the shortcut, so one from an older version is refreshed."""
    path = shortcut_path(project)
    link = _wscript_shell().CreateShortcut(path)
    link.TargetPath = _pythonw()
    link.Arguments = autostart_arguments(project)
    link.WorkingDirectory = project
    link.Description = 'ok-script child session agent (exits outside a child session)'
    link.Save()
    _remove_legacy_run_entry(project)
    logger.info(f'child session agent autostart installed: {path} -> {autostart_command(project)}')


def remove_autostart(project: str) -> bool:
    _remove_legacy_run_entry(project)
    try:
        os.remove(shortcut_path(project))
        logger.info('child session agent autostart removed')
        return True
    except OSError:
        return False


def window_spec(windows_config: dict) -> dict:
    """The parts of the app's ``windows`` config the agent needs to find the game window."""
    windows_config = windows_config or {}
    exe = windows_config.get('exe') or []
    return {
        'exe': [exe] if isinstance(exe, str) else list(exe),
        'hwnd_class': windows_config.get('hwnd_class'),
        'title': windows_config.get('title') if isinstance(windows_config.get('title'), str) else None,
    }


def write_agent_config(project: str, windows_config: dict, close_apps, elevate: bool = True) -> dict:
    data = {
        'window': window_spec(windows_config),
        'close_apps': [str(name) for name in (close_apps or []) if str(name).strip()],
        'elevate': bool(elevate),
    }
    protocol.write_json(protocol.config_file(project), data)
    return data
