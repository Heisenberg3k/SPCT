"""Use pythonw.exe so startup and child processes never create a console."""
from pathlib import Path
import traceback


if __name__ == "__main__":
    try:
        from screen_solver.app import main
        main([])
    except BaseException:
        # pythonw has no stderr. Save startup failures without a dialog.
        try:
            folder = Path(__file__).resolve().parent / "runtime"
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "startup_error.log").open("a", encoding="utf-8") as stream:
                traceback.print_exc(file=stream)
        except OSError:
            pass
