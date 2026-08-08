# -*- coding: utf-8 -*-
"""屏幕物理像素 <-> Qt 逻辑坐标换算工具。

背景
----
进程以 per-monitor DPI aware 运行（ok 在 OK.__init__ 里调用 SetProcessDpiAwareness(2)，
或打包 exe 的 manifest 已设置 DPI awareness），因此 Win32 API
（ClientToScreen / GetClientRect / GetWindowRect）返回的都是**物理像素**。
而 Qt 的 QWidget.setGeometry 使用的是**逻辑像素**。

Qt 的 QScreen.geometry() 在多 DPR 混合屏幕布局下，屏幕的**逻辑 origin 并不等于
物理 origin / 该屏 DPR**。实测（主屏 DPR=2.0，副屏在主屏左侧、DPR=1.25）：
副屏逻辑 origin = -1920，物理 origin 也是 -1920。若按旧算法 `物理 / DPR` 计算
逻辑坐标会得到 -1920/1.25 = -1536，Qt 再把窗口按副屏 DPR=1.25 映射回物理时，
overlay 就向右偏移了 (1920 - 1536) * 1.25 = 480px —— 这正是"覆盖层偏到游戏
窗口右侧（x 正方向）"的原因。

正确换算
--------
    logical = screen.geometry().origin + (physical - 屏幕物理origin) / screen.devicePixelRatio()

即：屏幕物理原点映射到 Qt 逻辑原点（QScreen.geometry().topLeft()），屏幕内部的
偏移再除以该屏幕的 devicePixelRatio。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes

import win32api
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication


def get_physical_screen_origin(px: int, py: int):
    """返回包含物理点 (px, py) 的显示器的物理左上角 (left, top)。"""
    try:
        pt = ctypes.wintypes.POINT(int(px), int(py))
        mon = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        info = win32api.GetMonitorInfo(int(mon))
        return info['Monitor'][0], info['Monitor'][1]
    except Exception:
        return int(px), int(py)


def get_physical_dpr(px: int, py: int) -> float:
    """返回物理点所在显示器的 DPI 缩放因子（GetDpiForMonitor / 96）。失败返回 1.0。"""
    try:
        pt = ctypes.wintypes.POINT(int(px), int(py))
        mon = ctypes.windll.user32.MonitorFromPoint(pt, 2)
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(int(mon), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        ratio = dpi_x.value / 96.0
        return ratio if ratio > 0 else 1.0
    except Exception:
        return 1.0


def screen_for_physical(px: int, py: int, dpr_hint: float = None):
    """把物理像素点映射到对应的 QScreen。

    QGuiApplication.screenAt 接受的是**逻辑坐标**。这里先用 物理坐标/该屏DPR 粗算
    逻辑坐标查询；失败则退回 primaryScreen。
    """
    try:
        dpr = dpr_hint if dpr_hint and dpr_hint > 0 else get_physical_dpr(px, py)
        guess = QPoint(int(round(px / dpr)), int(round(py / dpr)))
        screen = QGuiApplication.screenAt(guess)
        if screen is not None:
            return screen
        # 兜底：直接尝试物理坐标（在单屏 / 主屏 DPR=1 时等价）
        screen = QGuiApplication.screenAt(QPoint(int(round(px)), int(round(py))))
        if screen is not None:
            return screen
    except Exception:
        pass
    return QGuiApplication.primaryScreen()


def physical_rect_to_logical(px: int, py: int, pw: int, ph: int, dpr_hint: float = None):
    """把物理像素窗口 rect 换算为 Qt 逻辑坐标 (lx, ly, lw, lh)，正确处理混合 DPI 多屏。

    Args:
        px, py: 窗口左上角物理坐标。
        pw, ph: 窗口物理宽高。
        dpr_hint: 可选，调用方已知的该屏 DPR（如 ok 的 scaling 参数），用于加速定位屏幕。
    """
    try:
        screen = screen_for_physical(px, py, dpr_hint)
        dpr = float(screen.devicePixelRatio())
        dpr = dpr if dpr > 0 else 1.0
        lg = screen.geometry()
        ox, oy = get_physical_screen_origin(px, py)
        lx = lg.x() + (px - ox) / dpr
        ly = lg.y() + (py - oy) / dpr
        return lx, ly, pw / dpr, ph / dpr
    except Exception:
        dpr = dpr_hint if dpr_hint and dpr_hint > 0 else 1.0
        return px / dpr, py / dpr, pw / dpr, ph / dpr
