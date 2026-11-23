import json
import platform
import unittest
from unittest.mock import MagicMock, patch

from src.shape_packing.client.autostart import AutostartManager, main


class TestAutostartManager(unittest.TestCase):
    def test_autostart_supported(self):
        mgr = AutostartManager()
        self.assertIn(mgr.platform, ["windows", "darwin", "linux"])

    @patch("src.shape_packing.client.autostart.winreg", create=True)
    def test_windows_registry_enable_and_disable(self, mock_winreg):
        if platform.system().lower() != "windows":
            self.skipTest("Windows-specific registry test")

        mgr = AutostartManager()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.REG_SZ = 3

        # Test enable
        result = mgr.enable(minimized=True)
        self.assertTrue(result)
        mock_winreg.SetValueEx.assert_called()

        # Test disable
        result_dis = mgr.disable()
        self.assertTrue(result_dis)
        mock_winreg.DeleteValue.assert_called()

    def test_status_dict(self):
        mgr = AutostartManager()
        status = mgr.status()
        self.assertIn("platform", status)
        self.assertIn("enabled", status)
        self.assertIn("command", status)


if __name__ == "__main__":
    unittest.main()
