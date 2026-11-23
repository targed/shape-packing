from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Any, Dict, Optional

try:
    import winreg
except ImportError:
    winreg = None

APP_NAME = "ShapePackingWorker"
MACOS_PLIST_LABEL = "com.shapepacking.worker"


def get_worker_command(minimized: bool = True) -> str:
    """Resolve the appropriate Python executable and CLI invocation."""
    exe = sys.executable
    if platform.system().lower() == "windows":
        # Prefer pythonw.exe to prevent terminal popup window
        dirname, fname = os.path.split(exe)
        pythonw_candidate = os.path.join(dirname, "pythonw.exe")
        if os.path.exists(pythonw_candidate):
            exe = pythonw_candidate

    min_flag = " --minimized" if minimized else ""
    return f'"{exe}" -m src.shape_packing.client.gui{min_flag}'


class AutostartManager:
    """Manages cross-platform user-level autostart on system boot."""

    def __init__(self):
        self.platform = platform.system().lower()

    def is_enabled(self) -> bool:
        if self.platform == "windows":
            return self._is_enabled_windows()
        elif self.platform == "darwin":
            return self._is_enabled_macos()
        elif self.platform == "linux":
            return self._is_enabled_linux()
        return False

    def enable(self, minimized: bool = True) -> bool:
        cmd = get_worker_command(minimized=minimized)
        if self.platform == "windows":
            return self._enable_windows(cmd)
        elif self.platform == "darwin":
            return self._enable_macos(cmd)
        elif self.platform == "linux":
            return self._enable_linux(cmd)
        return False

    def disable(self) -> bool:
        if self.platform == "windows":
            return self._disable_windows()
        elif self.platform == "darwin":
            return self._disable_macos()
        elif self.platform == "linux":
            return self._disable_linux()
        return False

    def status(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "enabled": self.is_enabled(),
            "command": get_worker_command(minimized=True),
        }

    # --- Windows Implementation ---
    def _is_enabled_windows(self) -> bool:
        if winreg is None:
            return False
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
        except Exception:
            return False

    def _enable_windows(self, cmd: str) -> bool:
        if winreg is None:
            return False
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                return True
        except Exception:
            return False

    def _disable_windows(self) -> bool:
        if winreg is None:
            return False
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
                return True
        except getattr(winreg, "FileNotFoundError", FileNotFoundError):
            return True
        except Exception:
            return False

    # --- macOS Implementation ---
    def _get_macos_plist_path(self) -> str:
        return os.path.expanduser(f"~/Library/LaunchAgents/{MACOS_PLIST_LABEL}.plist")

    def _is_enabled_macos(self) -> bool:
        return os.path.exists(self._get_macos_plist_path())

    def _enable_macos(self, cmd: str) -> bool:
        plist_path = self._get_macos_plist_path()
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MACOS_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>src.shape_packing.client.gui</string>
        <string>--minimized</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        try:
            with open(plist_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def _disable_macos(self) -> bool:
        plist_path = self._get_macos_plist_path()
        if os.path.exists(plist_path):
            try:
                os.remove(plist_path)
                return True
            except Exception:
                return False
        return True

    # --- Linux Implementation ---
    def _get_linux_desktop_path(self) -> str:
        return os.path.expanduser("~/.config/autostart/shape-packing-worker.desktop")

    def _is_enabled_linux(self) -> bool:
        return os.path.exists(self._get_linux_desktop_path())

    def _enable_linux(self, cmd: str) -> bool:
        desktop_path = self._get_linux_desktop_path()
        os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=Shape Packing Worker
Comment=Distributed Shape Packing Volunteer Node
Exec={cmd}
Terminal=false
Categories=Utility;Math;Science;
"""
        try:
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def _disable_linux(self) -> bool:
        desktop_path = self._get_linux_desktop_path()
        if os.path.exists(desktop_path):
            try:
                os.remove(desktop_path)
                return True
            except Exception:
                return False
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed Shape Packing Autostart Service Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("enable", help="Enable automatic startup on login")
    subparsers.add_parser("disable", help="Disable automatic startup on login")

    status_parser = subparsers.add_parser("status", help="Query autostart configuration status")
    status_parser.add_argument("--json", action="store_true", help="Format output as JSON")

    args = parser.parse_args()
    mgr = AutostartManager()

    if args.command == "enable":
        ok = mgr.enable()
        print("Autostart successfully enabled." if ok else "Failed to enable autostart.")
        sys.exit(0 if ok else 1)
    elif args.command == "disable":
        ok = mgr.disable()
        print("Autostart successfully disabled." if ok else "Failed to disable autostart.")
        sys.exit(0 if ok else 1)
    elif args.command == "status":
        stat = mgr.status()
        if getattr(args, "json", False):
            print(json.dumps(stat, indent=2))
        else:
            print(f"Platform: {stat['platform']}")
            print(f"Autostart Enabled: {stat['enabled']}")
            print(f"Command: {stat['command']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
