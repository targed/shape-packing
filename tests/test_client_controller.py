from datetime import time as dt_time
import time
import unittest
from unittest.mock import MagicMock

from src.shape_packing.client.controller import (
    ScheduleConfig,
    WorkerController,
    WorkerState,
    is_within_schedule,
)
from src.shape_packing.client.native_worker import WorkerConfig


class TestWorkerController(unittest.TestCase):
    def test_schedule_evaluation(self):
        # Day schedule: 09:00 to 17:00
        day_sched = ScheduleConfig(enabled=True, start_time="09:00", end_time="17:00")
        self.assertTrue(is_within_schedule(dt_time(12, 0), day_sched.start, day_sched.end))
        self.assertFalse(is_within_schedule(dt_time(8, 59), day_sched.start, day_sched.end))
        self.assertFalse(is_within_schedule(dt_time(17, 1), day_sched.start, day_sched.end))

        # Night schedule across midnight: 22:00 to 07:00
        night_sched = ScheduleConfig(enabled=True, start_time="22:00", end_time="07:00")
        self.assertTrue(is_within_schedule(dt_time(23, 0), night_sched.start, night_sched.end))
        self.assertTrue(is_within_schedule(dt_time(3, 30), night_sched.start, night_sched.end))
        self.assertFalse(is_within_schedule(dt_time(12, 0), night_sched.start, night_sched.end))
        self.assertFalse(is_within_schedule(dt_time(21, 59), night_sched.start, night_sched.end))

    def test_start_pause_resume_stop_lifecycle(self):
        mock_cycle = MagicMock(return_value={"status": "completed", "attempts_completed": 50})
        controller = WorkerController(cycle_fn=mock_cycle)
        config = WorkerConfig(server_url="http://localhost:8000", username="tester", cores=2)

        # 1. Start
        controller.start(config)
        self.assertEqual(controller.get_state(), WorkerState.RUNNING)
        time.sleep(0.1)
        self.assertGreaterEqual(mock_cycle.call_count, 1)

        # 2. Pause
        controller.pause()
        self.assertEqual(controller.get_state(), WorkerState.PAUSED)
        current_calls = mock_cycle.call_count
        time.sleep(0.1)
        self.assertEqual(mock_cycle.call_count, current_calls)

        # 3. Resume
        controller.resume()
        self.assertEqual(controller.get_state(), WorkerState.RUNNING)
        time.sleep(0.1)
        self.assertGreater(mock_cycle.call_count, current_calls)

        # 4. Stop
        controller.stop()
        self.assertEqual(controller.get_state(), WorkerState.STOPPED)

    def test_snooze_functionality(self):
        mock_cycle = MagicMock(return_value={"status": "completed", "attempts_completed": 10})
        controller = WorkerController(cycle_fn=mock_cycle)
        config = WorkerConfig(server_url="http://localhost:8000", username="tester", cores=1)

        controller.start(config)
        # Snooze for 0.2 seconds (fraction of minute)
        controller.snooze(seconds=0.2)
        self.assertEqual(controller.get_state(), WorkerState.SNOOZED)
        self.assertGreater(controller.get_snooze_remaining_seconds(), 0)

        # Wait for snooze timer to lapse
        time.sleep(0.3)
        self.assertEqual(controller.get_state(), WorkerState.RUNNING)
        controller.stop()


if __name__ == "__main__":
    unittest.main()
