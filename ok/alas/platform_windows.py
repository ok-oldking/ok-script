import ctypes

from ok.alas.emulator_windows import Emulator, EmulatorInstance

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
            print(f'Cannot get MuMu instance index from name {instance.name}')
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
