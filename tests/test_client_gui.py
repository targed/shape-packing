import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.shape_packing.client.gui import (
    load_desktop_config,
    save_desktop_config,
    DesktopConfig,
    WorkerApp,
)


class TestGUIConfig(unittest.TestCase):
    def test_save_and_load_desktop_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            cfg = DesktopConfig(
                server_url="http://example.com:8000",
                username="alice",
                worker_id="w-1234",
                cores=6,
                autostart=True,
                schedule_enabled=True,
                schedule_start="23:00",
                schedule_end="06:30",
            )
            save_desktop_config(cfg, path=temp_path)

            loaded = load_desktop_config(path=temp_path)
            self.assertEqual(loaded.username, "alice")
            self.assertEqual(loaded.cores, 6)
            self.assertTrue(loaded.autostart)
            self.assertEqual(loaded.schedule_start, "23:00")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch("src.shape_packing.client.gui.TrayManager")
    def test_worker_app_initialization(self, mock_tray_cls):
        mock_tray = MagicMock()
        mock_tray_cls.return_value = mock_tray
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            app = WorkerApp(root, start_minimized=False)
            self.assertIsNotNone(app)
            self.assertIsNotNone(app.controller)
            self.assertIsNotNone(app.status_label)
            # Test UI slider interaction
            app._on_cores_slider("2")
            self.assertEqual(app.controller.config.cores, 2)
            app.tray.stop()
            app.controller.stop()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
