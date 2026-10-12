from __future__ import annotations

import argparse
import logging
import logging.handlers
import subprocess
import sys

from .config import BASE_DIR, load_settings


def configure_logging(runtime_dir) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        runtime_dir / "app.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def check(settings) -> int:
    from .copilot import resolve_cli

    print(f"Python: {sys.version.split()[0]}")
    print(f"Output: {settings.output_file}")
    if sys.platform != "win32":
        print("ERROR: Background hotkeys require Windows.")
        return 1
    try:
        from PIL import __version__ as pillow_version
        print(f"Pillow: {pillow_version}")
        command = resolve_cli(settings.resolved_cli())
        print(f"Copilot launcher: {command[0]}")
        result = subprocess.run(
            [*command, "--version"], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise RuntimeError("Copilot could not start. Run login.ps1/setup.ps1 in PowerShell.")
        print(f"Copilot: {result.stdout.strip()}")
        print("Local checks passed. Authentication and image support need a real request after login.ps1.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Windows screenshot-to-Python hotkeys")
    parser.add_argument("--check", action="store_true", help="Check local dependencies; does not send images")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.check:
        return check(settings)
    from .copilot import CopilotSettings, CopilotSolver
    from .controller import Controller
    from .windows import AlreadyRunningError, SingleInstance, WindowsDesktop, enable_dpi_awareness, run_hotkey_loop

    # A single process owns the global shortcuts and status file.
    try:
        with SingleInstance("Local\\SPCT_ScreenSolver"):
            configure_logging(settings.runtime_dir)
            enable_dpi_awareness()
            with WindowsDesktop() as desktop:
                solver = CopilotSolver(CopilotSettings(
                    cli_path=settings.resolved_cli(), model=settings.model,
                    timeout_seconds=settings.timeout_seconds,
                ))
                controller = Controller(settings, desktop, solver)
                try:
                    run_hotkey_loop(controller.handle, controller.tick)
                finally:
                    controller.close()
        return 0
    except AlreadyRunningError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
