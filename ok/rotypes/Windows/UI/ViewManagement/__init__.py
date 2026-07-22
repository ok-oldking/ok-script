from ctypes import Structure, c_int32, c_uint8

from ok.rotypes.idldsl import CtypesEnum, GUID, define_winrt_com_method
from ok.rotypes.inspectable import IInspectable
from ok.rotypes.roapi import GetActivationFactory


class UIColorType(CtypesEnum):
    Background = 0
    Foreground = 1
    AccentDark3 = 2
    AccentDark2 = 3
    AccentDark1 = 4
    Accent = 5
    AccentLight1 = 6
    AccentLight2 = 7
    AccentLight3 = 8
    Complement = 9


class Color(Structure):
    _fields_ = [
        ('alpha', c_uint8),
        ('red', c_uint8),
        ('green', c_uint8),
        ('blue', c_uint8),
    ]


@GUID('03021BE4-5254-4781-8194-5168F7D06D7B')
class IUISettings3(IInspectable):
    pass


define_winrt_com_method(
    IUISettings3,
    'GetColorValue',
    c_int32,
    retval=Color,
    vtbl=6,
)


def get_color_value(color_type):
    """Read a color from the Windows UI accent palette."""
    factory = GetActivationFactory('Windows.UI.ViewManagement.UISettings')
    settings = factory.ActivateInstance().astype(IUISettings3)
    return settings.GetColorValue(int(color_type))
