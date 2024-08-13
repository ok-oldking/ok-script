import ctypes
import os
import subprocess

from ok.alas.emulator_windows import Emulator, EmulatorInstance
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class EmulatorUnknown(Exception):
    pass


def get_focused_window():
    return ctypes.windll.user32.GetForegroundWindow()


def set_focus_window(hwnd):
    ctypes.windll.user32.SetForegroundWindow(hwnd)


def get_emulator_exe(instance: EmulatorInstance):
    """
    Start a emulator without error handling
    """
    exe = instance.emulator.path
    if instance == Emulator.MuMuPlayer:
        # NemuPlayer.exe
        return exe
    elif instance == Emulator.MuMuPlayerX:
        # NemuPlayer.exe -m nemu-12.0-x64-default
        return f'"{exe}" -m {instance.name}'
    elif instance == Emulator.MuMuPlayer12:
        # MuMuPlayer.exe -v 0
        if instance.MuMuPlayer12_id is None:
            logger.warning(f'Cannot get MuMu instance index from name {instance.name}')
        return f'"{exe}" -v {instance.MuMuPlayer12_id}'
    elif instance == Emulator.NoxPlayerFamily:
        # Nox.exe -clone:Nox_1
        return f'"{exe}" -clone:{instance.name}'
    elif instance == Emulator.BlueStacks5:
        # HD-Player.exe -instance Pie64
        return f'"{exe}" -instance {instance.name}'
    elif instance == Emulator.BlueStacks4:
        # BlueStacks\Client\Bluestacks.exe -vmname Android_1
        return f'"{exe}" -vmname {instance.name}'
    elif instance == Emulator.LDPlayerFamily:
        return f'"{exe}" -name {instance.name}'
    else:
        raise EmulatorUnknown(f'Cannot start an unknown emulator instance: {instance}')


def execute(game_path: str):
    if os.path.exists(game_path):
        try:
            subprocess.Popen(game_path, cwd=os.path.dirname(game_path), close_fds=True,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
            return True
        except Exception as e:
            logger.error('execute error', e)
