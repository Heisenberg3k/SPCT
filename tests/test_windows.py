"""Win32 ABI/lifecycle tests; never capture the screen, paste, or change clipboard."""

import ctypes
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from screen_solver import windows


class WindowsAbiTests(unittest.TestCase):
    def test_input_layout_matches_windows_sdk(self):
        pointer_size = ctypes.sizeof(ctypes.c_void_p)
        self.assertEqual(ctypes.sizeof(windows.INPUT), 40 if pointer_size == 8 else 28)
        self.assertEqual(ctypes.sizeof(windows.KEYBDINPUT), 24 if pointer_size == 8 else 16)
        self.assertEqual(ctypes.sizeof(windows.MOUSEINPUT), 32 if pointer_size == 8 else 24)
        self.assertEqual(windows.INPUT.value.offset, pointer_size)
        self.assertEqual(ctypes.sizeof(windows.MSG), 48 if pointer_size == 8 else 32)

    def test_registration_failure_cleans_up_prior_hotkeys(self):
        api = Mock()
        api.RegisterHotKey.side_effect = [True, True, False]
        with patch.object(windows, "_api", return_value=api):
            with patch.object(windows, "_error", return_value=OSError("conflict")):
                with self.assertRaises(OSError):
                    windows.run_hotkey_loop(Mock(), Mock())
        self.assertEqual([call.args[1] for call in api.UnregisterHotKey.call_args_list], [2, 1])
        api.SetTimer.assert_not_called()

    def test_timer_tick_and_exit_unregister_everything(self):
        api = Mock()
        api.SetTimer.return_value = 99
        pending = [(0x0113, 99), (0x0312, 4)]

        def next_message(pointer, *_args):
            message_id, parameter = pending.pop(0)
            message = ctypes.cast(pointer, ctypes.POINTER(windows.MSG)).contents
            message.message = message_id
            message.wParam = parameter
            return 1

        api.GetMessageW.side_effect = next_message
        on_hotkey, on_tick = Mock(), Mock()
        with patch.object(windows, "_api", return_value=api):
            windows.run_hotkey_loop(on_hotkey, on_tick)
        on_hotkey.assert_called_once_with("exit")
        on_tick.assert_called_once_with()
        api.KillTimer.assert_called_once_with(None, 99)
        self.assertEqual(api.UnregisterHotKey.call_count, 4)


@unittest.skipUnless(os.name == "nt", "native Win32 smoke tests require Windows")
class NativeWindowsTests(unittest.TestCase):
    def test_pointer_sized_function_results_are_declared(self):
        api = windows._api()
        for name in ("CreateMutexW", "GlobalAlloc", "GlobalLock", "CreateWindowExW", "SetClipboardData"):
            self.assertIs(getattr(api, name).restype, ctypes.c_void_p, name)
        self.assertIs(api.SetTimer.restype, ctypes.c_size_t)
        self.assertIs(api.DispatchMessageW.restype, ctypes.c_ssize_t)

    def test_mutex_prevents_duplicate_and_can_be_reacquired(self):
        name = "Local\\ScreenSolverTest-" + uuid.uuid4().hex
        with windows.SingleInstance(name):
            with self.assertRaises(windows.AlreadyRunningError):
                with windows.SingleInstance(name):
                    self.fail("Second instance acquired mutex")
        with windows.SingleInstance(name):
            pass

    def test_clipboard_owner_window_is_hidden(self):
        # No OpenClipboard / EmptyClipboard / SetClipboardData calls here.
        with windows.WindowsDesktop() as desktop:
            handle = desktop._owner_window()
            is_visible = windows._bind(desktop._api.user32, "IsWindowVisible", [windows.HWND], windows.BOOL)
            self.assertFalse(is_visible(handle))
            self.assertEqual(desktop._owner_window(), handle)

    def test_can_register_and_unregister_unused_hotkey(self):
        api = windows._api()
        identifier = 0x3EFF
        # F24 has no input injected and no callback executed.
        if not api.RegisterHotKey(None, identifier, 0x4000, 0x87):
            if ctypes.get_last_error() == 1409:
                self.skipTest("F24 is already registered on this desktop")
            raise windows._error("RegisterHotKey smoke test")
        self.assertTrue(api.UnregisterHotKey(None, identifier))

    def test_partial_input_failure_releases_injected_keys(self):
        fake_api = Mock()
        fake_api.GetAsyncKeyState.return_value = 0
        fake_api.SendInput.side_effect = [1, 2]
        with patch.object(windows, "_api", return_value=fake_api):
            desktop = windows.WindowsDesktop()
            with self.assertRaises(OSError):
                desktop.paste(click_at_pointer=False)
        cleanup = fake_api.SendInput.call_args_list[1].args[1]
        self.assertEqual([(event.ki.wVk, event.ki.dwFlags) for event in cleanup], [(ord("V"), 2), (0x11, 2)])

    def test_held_modifier_times_out_without_injecting_input(self):
        fake_api = Mock()
        fake_api.GetAsyncKeyState.return_value = -32768
        with patch.object(windows, "_api", return_value=fake_api):
            desktop = windows.WindowsDesktop()
            with self.assertRaises(TimeoutError):
                desktop.paste(release_timeout=0.001)
        fake_api.SendInput.assert_not_called()


if __name__ == "__main__":
    unittest.main()
