from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw

from .controller import WorkerController, WorkerState

logger = logging.getLogger(__name__)

COLOR_MAP = {
    WorkerState.RUNNING.value: "#22c55e",  # Green
    WorkerState.PAUSED.value: "#f59e0b",  # Amber
    WorkerState.SNOOZED.value: "#f59e0b",  # Amber
    WorkerState.SCHEDULED_IDLE.value: "#3b82f6",  # Blue
    WorkerState.ERROR.value: "#ef4444",  # Red
    WorkerState.STOPPED.value: "#64748b",  # Gray
}


def create_status_icon(state_or_color: str, size: int = 64) -> Image.Image:
    """Generate an in-memory RGBA circular status icon for the system tray."""
    color = COLOR_MAP.get(
        state_or_color,
        state_or_color if state_or_color.startswith("#") else "#64748b",
    )
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw outer antialiased circle
    margin = max(2, int(size * 0.08))
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color)

    # Draw inner subtle accent dot
    inner_m = int(size * 0.35)
    draw.ellipse((inner_m, inner_m, size - inner_m, size - inner_m), fill="#ffffff88")
    return image


class TrayManager:
    """Manages the pystray system tray icon and context menu."""

    def __init__(
        self,
        controller: Optional[WorkerController] = None,
        on_toggle_window: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ):
        self.controller = controller
        self.on_toggle_window = on_toggle_window
        self.on_quit = on_quit
        self._icon = None
        self._is_supported = False

        try:
            import pystray

            self._pystray = pystray
            self._is_supported = True
        except ImportError:
            self._pystray = None
            self._is_supported = False
            logger.info("pystray is not installed; running in standard window mode.")

    def is_supported(self) -> bool:
        return self._is_supported

    def start(self) -> None:
        """Start system tray icon in detached thread."""
        if not self._is_supported or not self._pystray:
            return

        icon_image = create_status_icon(WorkerState.STOPPED.value)
        menu = self._build_menu()
        self._icon = self._pystray.Icon(
            "ShapePackingWorker", icon_image, "Shape Packing Worker", menu=menu
        )

        # Run pystray in background thread so it doesn't block Tkinter
        t = threading.Thread(
            target=self._icon.run, daemon=True, name="SystemTrayThread"
        )
        t.start()

    def update_state(
        self, state: WorkerState, tooltip_text: Optional[str] = None
    ) -> None:
        """Update tray icon color and tooltip."""
        if not self._icon or not self._is_supported:
            return
        try:
            self._icon.icon = create_status_icon(state.value)
            if tooltip_text:
                self._icon.title = f"Shape Packing ({tooltip_text})"
        except Exception:
            pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def _build_menu(self):
        p = self._pystray

        def _pause_resume(icon, item):
            if self.controller:
                if self.controller.get_state() == WorkerState.RUNNING:
                    self.controller.pause()
                else:
                    self.controller.resume()

        def _snooze_30m(icon, item):
            if self.controller:
                self.controller.snooze(minutes=30)

        def _snooze_1h(icon, item):
            if self.controller:
                self.controller.snooze(minutes=60)

        def _toggle_win(icon, item):
            if self.on_toggle_window:
                self.on_toggle_window()

        def _quit_app(icon, item):
            if self.on_quit:
                self.on_quit()

        return p.Menu(
            p.MenuItem("Show/Hide Control Window", _toggle_win, default=True),
            p.Menu.SEPARATOR,
            p.MenuItem("Pause / Resume", _pause_resume),
            p.MenuItem("Snooze 30 min", _snooze_30m),
            p.MenuItem("Snooze 1 hour", _snooze_1h),
            p.Menu.SEPARATOR,
            p.MenuItem("Quit Worker", _quit_app),
        )
