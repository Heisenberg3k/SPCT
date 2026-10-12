import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from screen_solver.config import Settings, load_settings
from screen_solver.controller import Controller


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(output_file=root / "a.txt", runtime_dir=root / "runtime")
        self.desktop = Mock()
        self.solver = Mock()
        self.solver.solve.return_value = "print(42)\n"
        self.controller = Controller(self.settings, self.desktop, self.solver, capture=lambda: b"test png")

    def tearDown(self):
        self.controller.close()
        self.temp.cleanup()

    def finish(self):
        deadline = time.monotonic() + 3
        while self.controller.future is not None and time.monotonic() < deadline:
            self.controller.tick()
            time.sleep(0.005)
        self.assertIsNone(self.controller.future)

    def test_capture_solve_save_copy_and_paste(self):
        self.controller.handle("capture")
        self.controller.handle("solve")
        self.finish()
        self.assertEqual(self.settings.output_file.read_text(), "print(42)\n")
        self.desktop.copy_text.assert_called_with("print(42)\n")
        self.controller.handle("paste")
        self.desktop.paste.assert_called_once_with(click_at_pointer=True)
        self.assertEqual(list(self.settings.runtime_dir.glob("request-*")), [])

    def test_no_capture_or_solution_does_not_send_or_paste(self):
        self.controller.handle("solve")
        self.controller.handle("paste")
        self.solver.solve.assert_not_called()
        self.desktop.paste.assert_not_called()

    def test_error_preserves_previous_file_and_does_not_copy(self):
        self.settings.output_file.write_text("old code")
        self.solver.solve.side_effect = RuntimeError("Authentication required")
        self.controller.handle("capture")
        self.controller.handle("solve")
        self.finish()
        self.assertEqual(self.settings.output_file.read_text(), "old code")
        self.desktop.copy_text.assert_not_called()
        self.assertEqual(self.controller.stage, "error")

    def test_new_capture_cancels_and_discards_old_result(self):
        started = threading.Event()

        def delayed(path, work, cancel):
            self.assertEqual(path.read_bytes(), b"test png")
            started.set()
            self.assertTrue(cancel.wait(2))
            return "print('stale')\n"

        self.solver.solve.side_effect = delayed
        self.controller.handle("capture")
        self.controller.handle("solve")
        self.assertTrue(started.wait(1))
        self.controller.capture = lambda: b"new png"
        self.controller.handle("capture")
        self.finish()
        self.assertFalse(self.settings.output_file.exists())
        self.desktop.copy_text.assert_not_called()
        self.assertEqual(self.controller.stage, "captured")

    def test_clipboard_failure_keeps_saved_solution_retryable(self):
        self.desktop.copy_text.side_effect = OSError("Clipboard busy")
        self.controller.handle("capture")
        self.controller.handle("solve")
        self.finish()
        self.assertEqual(self.settings.output_file.read_text(), "print(42)\n")
        self.assertEqual(self.controller.solution, "print(42)\n")
        self.desktop.copy_text.side_effect = None
        self.controller.handle("paste")
        self.desktop.paste.assert_called_once()

    def test_close_cancels_worker(self):
        started = threading.Event()

        def blocked(path, work, cancel):
            started.set()
            cancel.wait(2)
            return "print(1)\n"

        self.solver.solve.side_effect = blocked
        self.controller.handle("capture")
        self.controller.handle("solve")
        self.assertTrue(started.wait(1))
        self.controller.handle("exit")
        self.assertTrue(self.controller.stopped)
        self.assertFalse(self.settings.output_file.exists())
        state = json.loads((self.settings.runtime_dir / "status.json").read_text())
        self.assertEqual(state["stage"], "stopped")
        self.assertFalse(state["solving"])


class ConfigTests(unittest.TestCase):
    def test_reject_invalid_timeout_and_unknown_option(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in ({"timeout_seconds": 0}, {"timeout_seconds": True}, {"typo": 1}, {"click_at_pointer": "false"}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    load_settings(path)


if __name__ == "__main__":
    unittest.main()
