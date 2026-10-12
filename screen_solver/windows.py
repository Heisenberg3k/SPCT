"""Small, windowless Win32 adapter. Importing this module has no UI side effects.

Only explicit calls register hotkeys, replace clipboard contents, or send input.
Clipboard work and ``close()`` must run on the thread that created its owner
window (normally the thread running ``run_hotkey_loop``).
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from collections.abc import Callable
from functools import lru_cache


# Fixed-width Windows types are deliberate: c_long has a different width on Unix.
DWORD = UINT = ctypes.c_uint32
LONG = BOOL = ctypes.c_int32
WORD = ctypes.c_uint16
HANDLE = HWND = ctypes.c_void_p
WPARAM = ULONG_PTR = ctypes.c_size_t
LPARAM = LRESULT = ctypes.c_ssize_t


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
        ("lParam", LPARAM), ("time", DWORD), ("pt", POINT),
        ("lPrivate", DWORD),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
        ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
        ("time", DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", DWORD), ("value", _INPUTUNION)]


class AlreadyRunningError(RuntimeError):
    """Another process holds this application's named mutex."""


def _error(operation: str, code: int | None = None) -> OSError:
    code = ctypes.get_last_error() if code is None else code
    message = ctypes.FormatError(code).strip() if code else "Windows rejected the operation"
    return OSError(code, f"{operation}: {message}")


def _bind(library: object, name: str, args: list[object], result: object):
    function = getattr(library, name)
    function.argtypes = args
    function.restype = result
    return function


class _WindowsAPI:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("This application requires Windows.")
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = user
        self.CreateMutexW = _bind(kernel, "CreateMutexW", [ctypes.c_void_p, BOOL, ctypes.c_wchar_p], HANDLE)
        self.CloseHandle = _bind(kernel, "CloseHandle", [HANDLE], BOOL)
        self.GlobalAlloc = _bind(kernel, "GlobalAlloc", [UINT, ctypes.c_size_t], HANDLE)
        self.GlobalLock = _bind(kernel, "GlobalLock", [HANDLE], ctypes.c_void_p)
        self.GlobalUnlock = _bind(kernel, "GlobalUnlock", [HANDLE], BOOL)
        self.GlobalFree = _bind(kernel, "GlobalFree", [HANDLE], HANDLE)
        self.GetModuleHandleW = _bind(kernel, "GetModuleHandleW", [ctypes.c_wchar_p], HANDLE)
        self.CreateWindowExW = _bind(user, "CreateWindowExW", [
            DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            HWND, HANDLE, HANDLE, ctypes.c_void_p,
        ], HWND)
        self.DestroyWindow = _bind(user, "DestroyWindow", [HWND], BOOL)
        self.OpenClipboard = _bind(user, "OpenClipboard", [HWND], BOOL)
        self.EmptyClipboard = _bind(user, "EmptyClipboard", [], BOOL)
        self.CloseClipboard = _bind(user, "CloseClipboard", [], BOOL)
        self.SetClipboardData = _bind(user, "SetClipboardData", [UINT, HANDLE], HANDLE)
        self.GetAsyncKeyState = _bind(user, "GetAsyncKeyState", [ctypes.c_int], ctypes.c_int16)
        self.SendInput = _bind(user, "SendInput", [UINT, ctypes.POINTER(INPUT), ctypes.c_int], UINT)
        self.RegisterHotKey = _bind(user, "RegisterHotKey", [HWND, ctypes.c_int, UINT, UINT], BOOL)
        self.UnregisterHotKey = _bind(user, "UnregisterHotKey", [HWND, ctypes.c_int], BOOL)
        self.SetTimer = _bind(user, "SetTimer", [HWND, ULONG_PTR, UINT, ctypes.c_void_p], ULONG_PTR)
        self.KillTimer = _bind(user, "KillTimer", [HWND, ULONG_PTR], BOOL)
        self.GetMessageW = _bind(user, "GetMessageW", [ctypes.POINTER(MSG), HWND, UINT, UINT], BOOL)
        self.TranslateMessage = _bind(user, "TranslateMessage", [ctypes.POINTER(MSG)], BOOL)
        self.DispatchMessageW = _bind(user, "DispatchMessageW", [ctypes.POINTER(MSG)], LRESULT)


@lru_cache(maxsize=1)
def _api() -> _WindowsAPI:
    return _WindowsAPI()


class SingleInstance:
    """Keep a named mutex handle alive without acquiring mutex ownership."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._handle: int | None = None

    def __enter__(self) -> SingleInstance:
        if self._handle is not None:
            raise RuntimeError("SingleInstance is already entered.")
        api = _api()
        ctypes.set_last_error(0)
        handle = api.CreateMutexW(None, False, self.name)
        code = ctypes.get_last_error()
        if not handle:
            raise _error("CreateMutexW", code)
        if code == 183:  # ERROR_ALREADY_EXISTS
            api.CloseHandle(handle)
            raise AlreadyRunningError("Another instance is already running.")
        self._handle = handle
        return self

    def close(self) -> None:
        if self._handle is not None:
            _api().CloseHandle(self._handle)
            self._handle = None

    def __exit__(self, *_exc: object) -> None:
        self.close()


def enable_dpi_awareness() -> None:
    """Use physical monitor coordinates; tolerate awareness set by the host."""
    api = _api()
    try:
        set_context = _bind(api.user32, "SetProcessDpiAwarenessContext", [HANDLE], BOOL)
    except AttributeError:
        pass
    else:
        if set_context(HANDLE(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            return
        if ctypes.get_last_error() == 5:  # ERROR_ACCESS_DENIED: already configured
            return
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_awareness = _bind(shcore, "SetProcessDpiAwareness", [ctypes.c_int], LONG)
        result = set_awareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        if result in (0, -2147024891):  # S_OK / E_ACCESSDENIED
            return
    except (OSError, AttributeError):
        pass
    set_aware = _bind(api.user32, "SetProcessDPIAware", [], BOOL)
    if not set_aware():
        raise _error("SetProcessDPIAware")


def _key(vk: int, *, up: bool = False) -> INPUT:
    value = INPUT(type=1)  # INPUT_KEYBOARD
    value.ki = KEYBDINPUT(vk, 0, 0x0002 if up else 0, 0, 0)
    return value


def _mouse(flags: int) -> INPUT:
    value = INPUT(type=0)  # INPUT_MOUSE
    value.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return value


class WindowsDesktop:
    def __init__(self) -> None:
        self._api = _api()
        self._clipboard_window: int | None = None
        self._owner_thread: int | None = None

    def _owner_window(self) -> int:
        current = threading.get_ident()
        if self._clipboard_window is not None:
            if self._owner_thread != current:
                raise RuntimeError("Clipboard operations must use their window's original thread.")
            return self._clipboard_window
        # A message-only STATIC window has no visible UI and never takes focus.
        window = self._api.CreateWindowExW(
            0, "STATIC", "ScreenSolverClipboardOwner", 0, 0, 0, 0, 0,
            HWND(-3), None, self._api.GetModuleHandleW(None), None,
        )
        if not window:
            raise _error("CreateWindowExW")
        self._clipboard_window = window
        self._owner_thread = current
        return window

    def copy_text(self, text: str) -> None:
        """Replace the Windows clipboard with Unicode text, retrying contention."""
        if "\x00" in text:
            raise ValueError("Clipboard text cannot contain NUL characters.")
        # Windows CF_UNICODETEXT is UTF-16LE, including a terminating UTF-16 NUL.
        data = (text + "\x00").encode("utf-16-le")
        owner = self._owner_window()
        memory = self._api.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not memory:
            raise _error("GlobalAlloc")
        opened = False
        transferred = False
        try:
            pointer = self._api.GlobalLock(memory)
            if not pointer:
                raise _error("GlobalLock")
            try:
                ctypes.memmove(pointer, data, len(data))
            finally:
                self._api.GlobalUnlock(memory)
            deadline = time.monotonic() + 1.5
            while not self._api.OpenClipboard(owner):
                if time.monotonic() >= deadline:
                    raise _error("OpenClipboard (clipboard busy)")
                time.sleep(0.03)
            opened = True
            if not self._api.EmptyClipboard():
                raise _error("EmptyClipboard")
            if not self._api.SetClipboardData(13, memory):  # CF_UNICODETEXT
                raise _error("SetClipboardData")
            transferred = True  # Windows now owns the allocation.
        finally:
            if opened:
                self._api.CloseClipboard()
            if not transferred:
                self._api.GlobalFree(memory)

    def paste(self, click_at_pointer: bool = True, release_timeout: float = 3.0) -> None:
        """Wait for the hotkey to be released, optionally click, then send Ctrl+V.

        Windows blocks input sent to applications at a higher integrity level.
        A blocked injection raises OSError; it never triggers an elevation prompt.
        """
        if release_timeout <= 0:
            raise ValueError("release_timeout must be greater than zero.")
        deadline = time.monotonic() + release_timeout
        # Include Windows keys so an unrelated chord cannot become Win+Ctrl+V.
        keys = (0x10, 0x11, 0x12, ord("O"), 0x5B, 0x5C)
        while any(self._api.GetAsyncKeyState(vk) & 0x8000 for vk in keys):
            if time.monotonic() >= deadline:
                raise TimeoutError("Release Ctrl, Shift, Alt, O and Windows keys before pasting.")
            time.sleep(0.01)
        events = []
        if click_at_pointer:
            events.extend((_mouse(0x0002), _mouse(0x0004)))  # LEFTDOWN / LEFTUP
        events.extend((_key(0x11), _key(ord("V")), _key(ord("V"), up=True), _key(0x11, up=True)))
        inputs = (INPUT * len(events))(*events)
        ctypes.set_last_error(0)
        sent = self._api.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            code = ctypes.get_last_error()
            if sent:
                # A partial insertion must not leave our Ctrl/V or mouse down.
                releases = [_key(ord("V"), up=True), _key(0x11, up=True)]
                if click_at_pointer:
                    releases.append(_mouse(0x0004))
                cleanup = (INPUT * len(releases))(*releases)
                self._api.SendInput(len(cleanup), cleanup, ctypes.sizeof(INPUT))
            raise _error("SendInput (target may be elevated)", code)

    def close(self) -> None:
        if self._clipboard_window is not None:
            if self._owner_thread != threading.get_ident():
                raise RuntimeError("Close the clipboard window on its original thread.")
            if not self._api.DestroyWindow(self._clipboard_window):
                raise _error("DestroyWindow")
            self._clipboard_window = None
            self._owner_thread = None

    def __enter__(self) -> WindowsDesktop:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def run_hotkey_loop(
    on_hotkey: Callable[[str], None],
    on_tick: Callable[[], None],
) -> None:
    """Dispatch global Ctrl+Shift+Q/E/O/X and poll completions every 50 ms.

    Callbacks run on the calling thread. They should return promptly; long work
    belongs in a worker, with its completion handled by ``on_tick``.
    Registration conflicts raise OSError and unwind all earlier registrations.
    """
    api = _api()
    hotkeys = {1: ("Q", "capture"), 2: ("E", "solve"), 3: ("O", "paste"), 4: ("X", "exit")}
    registered: list[int] = []
    timer = 0
    try:
        for identifier, (key, _action) in hotkeys.items():
            if not api.RegisterHotKey(None, identifier, 0x0002 | 0x0004 | 0x4000, ord(key)):
                raise _error(f"RegisterHotKey Ctrl+Shift+{key} (possibly already in use)")
            registered.append(identifier)
        timer = api.SetTimer(None, 0, 50, None)
        if not timer:
            raise _error("SetTimer")
        message = MSG()
        while True:
            result = api.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == -1:
                raise _error("GetMessageW")
            if result == 0:  # WM_QUIT
                break
            if message.message == 0x0312 and message.wParam in hotkeys:  # WM_HOTKEY
                action = hotkeys[message.wParam][1]
                on_hotkey(action)
                if action == "exit":
                    break
            elif message.message == 0x0113 and message.wParam == timer:  # WM_TIMER
                on_tick()
            else:
                api.TranslateMessage(ctypes.byref(message))
                api.DispatchMessageW(ctypes.byref(message))
    finally:
        if timer:
            api.KillTimer(None, timer)
        for identifier in reversed(registered):
            api.UnregisterHotKey(None, identifier)
