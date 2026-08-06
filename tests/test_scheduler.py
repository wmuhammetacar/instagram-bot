import json
import time
import unittest

from insta_bot.scheduler import compute_next_run, is_due

SUN, MON, TUE = 0, 1, 2


class TestScheduler(unittest.TestCase):
    def test_interval(self):
        last = 1000.0
        self.assertEqual(compute_next_run({"every_hours": 4}, last_run=last), last + 4 * 3600)

    def test_interval_no_last_run(self):
        now = time.time()
        nxt = compute_next_run({"every_hours": 2})
        self.assertAlmostEqual(nxt, now + 2 * 3600, delta=5)

    def test_at_times_today(self):
        tm = time.localtime()
        hhmm = f"{tm.tm_hour:02d}:{(tm.tm_min + 5) % 60:02d}"
        nxt = compute_next_run({"at": [hhmm]}, now=time.time())
        self.assertIsNotNone(nxt)
        self.assertGreater(nxt, time.time())

    def test_at_time_today_passed_goes_tomorrow(self):
        tm = time.localtime()
        hhmm = f"{(tm.tm_hour - 1) % 24:02d}:{tm.tm_min:02d}"
        nxt = compute_next_run({"at": [hhmm], "days": [tm.tm_wday]}, now=time.time())
        self.assertGreater(nxt - time.time(), 20 * 3600)

    def test_no_schedule(self):
        self.assertIsNone(compute_next_run({}))

    def test_is_due(self):
        self.assertTrue(is_due({"enabled": 1, "next_run": 1.0}))
        self.assertFalse(is_due({"enabled": 1, "next_run": 10**18}))
        self.assertFalse(is_due({"enabled": 0, "next_run": 1.0}))
        self.assertFalse(is_due({"enabled": 1, "next_run": None}))


if __name__ == "__main__":
    unittest.main()
