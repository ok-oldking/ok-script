from ctypes import c_uint32, c_bool, c_double

from ok.rotypes.Windows.Foundation import IReference, Rect, IAsyncOperation
from ok.rotypes.Windows.Foundation.Collections import IVectorView
from ok.rotypes.Windows.Globalization import Language
from ok.rotypes.Windows.Graphics.Imaging import SoftwareBitmap
from ok.rotypes.idldsl import define_winrt_com_method, _static_propget, _static_method, _non_activatable_init, \
    runtimeclass, GUID
from ok.rotypes.inspectable import IInspectable
from ok.rotypes.winstring import HSTRING


@GUID('3C2A477A-5CD9-3525-BA2A-23D1E0A68A1D')
class IOcrWord(IInspectable):
    pass


@GUID('0043A16F-E31F-3A24-899C-D444BD088124')
class IOcrLine(IInspectable):
    pass


@GUID('9BD235B2-175B-3D6A-92E2-388C206E2F63')
class IOcrResult(IInspectable):
    pass


@GUID('5A14BC41-5B76-3140-B680-8825562683AC')
class IOcrEngine(IInspectable):
    pass


@GUID('5BFFA85A-3384-3540-9940-699120D428A8')
class IOcrEngineStatics(IInspectable):
    pass


class OcrWord(runtimeclass, IOcrWord):
    pass


class OcrLine(runtimeclass, IOcrLine):
    pass


class OcrResult(runtimeclass, IOcrResult):
    pass


class OcrEngine(runtimeclass, IOcrEngine):
    __init__ = _non_activatable_init
    MaxImageDimension = _static_propget(IOcrEngineStatics, 'MaxImageDimension')
    AvailableRecognizerLanguages = _static_propget(IOcrEngineStatics, 'AvailableRecognizerLanguages')
    IsLanguageSupported = _static_method(IOcrEngineStatics, 'IsLanguageSupported')
    TryCreateFromLanguage = _static_method(IOcrEngineStatics, 'TryCreateFromLanguage')
    TryCreateFromUserProfileLanguages = _static_method(IOcrEngineStatics, 'TryCreateFromUserProfileLanguages')


define_winrt_com_method(IOcrWord, 'get_BoundingRect', propget=Rect, vtbl=6)
define_winrt_com_method(IOcrWord, 'get_Text', propget=HSTRING, vtbl=7)

define_winrt_com_method(IOcrLine, 'get_Words', propget=IVectorView(OcrWord), vtbl=6)
define_winrt_com_method(IOcrLine, 'get_Text', propget=HSTRING, vtbl=7)

define_winrt_com_method(IOcrResult, 'get_Lines', propget=IVectorView(OcrLine), vtbl=6)
define_winrt_com_method(IOcrResult, 'get_TextAngle', propget=IReference(c_double), vtbl=7)
define_winrt_com_method(IOcrResult, 'get_Text', propget=HSTRING, vtbl=8)

define_winrt_com_method(IOcrEngine, 'RecognizeAsync', SoftwareBitmap, retval=IAsyncOperation(OcrResult), vtbl=6)
define_winrt_com_method(IOcrEngine, 'get_RecognizerLanguage', propget=Language, vtbl=7)

define_winrt_com_method(IOcrEngineStatics, 'get_MaxImageDimension', propget=c_uint32, vtbl=6)
define_winrt_com_method(IOcrEngineStatics, 'get_AvailableRecognizerLanguages', propget=IVectorView(Language), vtbl=7)
define_winrt_com_method(IOcrEngineStatics, 'IsLanguageSupported', Language, retval=c_bool, vtbl=8)
define_winrt_com_method(IOcrEngineStatics, 'TryCreateFromLanguage', Language, retval=IOcrEngine, vtbl=9)
define_winrt_com_method(IOcrEngineStatics, 'TryCreateFromUserProfileLanguages', retval=IOcrEngine, vtbl=10)
