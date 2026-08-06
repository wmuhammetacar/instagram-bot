import threading
import time
import unittest
from types import SimpleNamespace

from insta_bot.db import Repo
from insta_bot.scheduler import Scheduler, compute_next_run, is_due

SUN, MON, TUE = 0, 1, 2

SILENT = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                         error=lambda *a, **k: None)


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

    def test_at_times_picks_earliest_today(self):
        # Regresyon: sirasiz saatlerde en erken olan secilmeli (liste sirasi degil).
        now = time.mktime((2026, 8, 6, 8, 0, 0, 0, 0, -1))  # 08:00
        nxt = compute_next_run({"at": ["21:00", "09:00"]}, now=now)
        self.assertEqual(time.localtime(nxt).tm_hour, 9)

    def test_at_times_tomorrow_earliest(self):
        # Bugun tum saatler gectiyse yarinin en erken saati secilmeli.
        now = time.mktime((2026, 8, 6, 23, 0, 0, 0, 0, -1))  # 23:00
        nxt = compute_next_run({"at": ["21:00", "09:00"]}, now=now)
        self.assertEqual(time.localtime(nxt).tm_hour, 9)
        self.assertGreater(nxt, now)

    def test_no_schedule(self):
        self.assertIsNone(compute_next_run({}))

    def test_is_due(self):
        self.assertTrue(is_due({"enabled": 1, "next_run": 1.0}))
        self.assertFalse(is_due({"enabled": 1, "next_run": 10**18}))
        self.assertFalse(is_due({"enabled": 0, "next_run": 1.0}))
        self.assertFalse(is_due({"enabled": 1, "next_run": None}))


class FakeConfig:
    def tasks(self):
        return []


class TestSchedulerLock(unittest.TestCase):
    """Regresyon: hesap kilidi gorev BITENE kadar tutulmali (onceden submit'ten
    hemen sonra birakiliyordu, ayni hesap paralel calisabiliyordu)."""

    def _make(self, engage_fn):
        sched = Scheduler(FakeConfig(), Repo(":memory:"), SimpleNamespace(engage=engage_fn),
                          SILENT, provider=lambda name: object())
        return sched

    def test_lock_held_until_task_finishes(self):
        started = threading.Event()
        release = threading.Event()

        def engage(client, account, **kw):
            started.set()
            release.wait(3)

        sched = self._make(engage)
        task = {"id": 1, "name": "t", "account": "a", "action": "engage",
                "params": "{}", "schedule": "{}"}
        sched._dispatch(task)
        self.assertTrue(started.wait(3), "gorev baslamadi")

        # Gorev calisirken kilit hala tutuluyor olmali
        lock = sched._busy["a"]
        self.assertFalse(lock.acquire(blocking=False))

        # Ikinci dispatch mesgul oldugu icin atlanmali (submit edilmemeli)
        sched._dispatch(task)

        release.set()
        # Gorev bitince kilit birakilmali
        freed = False
        for _ in range(300):
            if lock.acquire(blocking=False):
                lock.release()
                freed = True
                break
            time.sleep(0.01)
        self.assertTrue(freed, "gorev bittikten sonra kilit birakilmadi")
        sched.stop()


if __name__ == "__main__":
    unittest.main()
