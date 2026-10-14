"""Thanh tiến độ trên nút của tool ở taskbar Windows (ITaskbarList3), để thấy tiến độ cả khi đang làm việc khác.

Gọi COM bằng ctypes (không cần thư viện thêm). Lỗi gì cũng bỏ qua: taskbar chỉ là phần thêm.
Thứ tự hàm trong bảng ảo: IUnknown (0–2), ITaskbarList (HrInit 3 … 7), ITaskbarList2 (8),
ITaskbarList3: SetProgressValue 9, SetProgressState 10.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITASKBAR_LIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
CLSCTX_INPROC_SERVER = 1

NONE = 0           # không hiện thanh
INDETERMINATE = 1  # thanh chạy qua lại
NORMAL = 2
ERROR = 4          # thanh đỏ
PAUSED = 8         # thanh vàng


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                ("data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _Guid:
    value = _Guid()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(value))
    return value


class TaskbarProgress:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._ptr: ctypes.c_void_p | None = None
        self.state = NONE
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)  # đã khởi tạo rồi thì trả S_FALSE, không sao
            pointer = ctypes.c_void_p()
            clsid, iid = _guid(CLSID_TASKBAR_LIST), _guid(IID_ITASKBAR_LIST3)
            result = ole32.CoCreateInstance(ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER, ctypes.byref(iid),
                                            ctypes.byref(pointer))
            if result != 0 or not pointer.value:
                log.info("Không dùng được tiến độ trên taskbar (mã 0x%08X)", result & 0xFFFFFFFF)
                return
            self._ptr = pointer
            self._method(3)(self._ptr)  # HrInit
        except (OSError, AttributeError, ValueError) as exc:
            log.info("Không dùng được tiến độ trên taskbar: %s", exc)
            self._ptr = None

    @property
    def available(self) -> bool:
        return self._ptr is not None

    def _method(self, index: int, *argtypes):
        vtable = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return prototype(vtable[index])

    def set_state(self, state: int) -> None:
        if self._ptr is None or state == self.state:
            return
        try:
            self._method(10, wintypes.HWND, ctypes.c_int)(self._ptr, self.hwnd, state)
            self.state = state
        except OSError:
            pass

    def set_value(self, fraction: float, state: int = NORMAL) -> None:
        """Hiện thanh ở `fraction` (0–1)."""
        if self._ptr is None:
            return
        self.set_state(state)
        try:
            done = int(max(0.0, min(1.0, fraction)) * 1000)
            self._method(9, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)(self._ptr, self.hwnd, done, 1000)
        except OSError:
            pass
