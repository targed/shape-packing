import unittest
from PIL import Image
from src.shape_packing.client.controller import WorkerState
from src.shape_packing.client.tray import TrayManager, create_status_icon


class TestTrayManager(unittest.TestCase):
    def test_create_status_icon(self):
        icon_img = create_status_icon("green", size=32)
        self.assertIsInstance(icon_img, Image.Image)
        self.assertEqual(icon_img.size, (32, 32))

        # Check all color states generate valid images
        for state in [
            WorkerState.RUNNING,
            WorkerState.PAUSED,
            WorkerState.SNOOZED,
            WorkerState.SCHEDULED_IDLE,
            WorkerState.ERROR,
            WorkerState.STOPPED,
        ]:
            img = create_status_icon(state.value, size=16)
            self.assertIsNotNone(img)

    def test_tray_manager_initialization(self):
        tray = TrayManager(on_toggle_window=lambda: None, on_quit=lambda: None)
        self.assertIsNotNone(tray)
        # Should gracefully report whether system tray is supported
        self.assertIsInstance(tray.is_supported(), bool)


if __name__ == "__main__":
    unittest.main()
