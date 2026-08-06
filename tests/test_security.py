import time
import unittest
from unittest.mock import patch

from insta_bot.db import Repo
from insta_bot.security import CooldownRegistry, DelayEngine, LimitEngine, in_window

LIMITS_CFG = {"limits": {"follows": 60, "likes": 150, "comments": 20, "dms": 20,
                         "posts": 4, "hourly_cap_fraction": 0.2}}


class TestDelayEngine(unittest.TestCase):
    def test_bounds(self):
        cfg = {"delays": {"base": [45, 120], "spread": [10, 60], "heat_multiplier": 2.0,
                          "heat_after": 25, "after_error": 300, "min": 5}}
        engine = DelayEngine(cfg)
        for _ in range(200):
            d = engine.compute("like", actions_done=0)
            self.assertGreaterEqual(d, 5)
            self.assertLess(d, 60 * 60)

    def test_heat_grows(self):
        cfg = {"delays": {"base": [10, 10], "spread": [0, 0], "heat_multiplier": 2.0,
                          "heat_after": 25, "after_error": 300, "min": 5}}
        engine = DelayEngine(cfg)
        cold = engine.compute("follow", actions_done=0)
        hot = engine.compute("follow", actions_done=100)
        self.assertGreater(hot, cold)

    def test_after_error_floor(self):
        cfg = {"delays": {"base": [10, 10], "spread": [0, 0], "heat_multiplier": 0,
                          "heat_after": 25, "after_error": 300, "min": 5}}
        engine = DelayEngine(cfg)
        self.assertGreaterEqual(engine.compute("like", after_error=True), 300)

    def test_pause_sleeps(self):
        cfg = {"delays": {"base": [0.01, 0.02], "spread": [0, 0], "heat_multiplier": 0,
                          "heat_after": 25, "after_error": 300, "min": 0.001}}
        engine = DelayEngine(cfg)
        with patch("insta_bot.security.time.sleep") as sleep:
            engine.pause("like")
            sleep.assert_called_once()


class TestLimitEngine(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(":memory:")
        self.engine = LimitEngine(LIMITS_CFG, self.repo)

    def test_checks_and_consume(self):
        self.assertTrue(self.engine.check("a", "follows"))
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.assertEqual(self.engine.remaining("a", "follows"), 58)
        self.assertTrue(self.engine.check("a", "follows"))
        for _ in range(self.engine.hourly_cap("follows")):
            self.engine.consume("a", "follows")
        self.assertFalse(self.engine.check("a", "follows"))

    def test_hourly_cap(self):
        self.assertEqual(self.engine.hourly_cap("follows"), 12)
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.engine.consume("a", "follows")
        self.assertFalse(self.engine.check("a", "follows"))

    def test_daily_isolated(self):
        self.engine.consume("a", "follows")
        self.assertFalse(self.engine.check("a", "likes") is None)


class TestCooldownRegistry(unittest.TestCase):
    def test_set_and_expire(self):
        repo = Repo(":memory:")
        reg = CooldownRegistry(repo)
        reg.set("a", "sentry", 60)
        self.assertTrue(reg.active("a", "sentry"))
        reg.set("a", "sentry", -10)
        self.assertFalse(reg.active("a", "sentry"))


class TestWindows(unittest.TestCase):
    def test_empty_windows_always_open(self):
        self.assertTrue(in_window({}))

    def test_hour_match(self):
        cfg = {"windows": {"hours": [time.localtime().tm_hour]}}
        self.assertTrue(in_window(cfg))

    def test_hour_miss(self):
        cfg = {"windows": {"hours": [(time.localtime().tm_hour + 1) % 24]}}
        self.assertFalse(in_window(cfg))

    def test_timezone_hour_used(self):
        # Regresyon: pencere saati config timezone'una gore hesaplanmali.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = "Europe/Istanbul"
        hour = datetime.now(ZoneInfo(tz)).hour
        self.assertTrue(in_window({"windows": {"hours": [hour], "timezone": tz}}))
        self.assertFalse(in_window({"windows": {"hours": [(hour + 1) % 24], "timezone": tz}}))

    def test_tz_name_argument(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hour = datetime.now(ZoneInfo("UTC")).hour
        self.assertTrue(in_window({"windows": {"hours": [hour]}}, tz_name="UTC"))

    def test_explicit_now_overrides_tz(self):
        # now verilirse timezone yok sayilir (geriye donuk uyumluluk).
        struct = time.struct_time((2026, 8, 6, 14, 0, 0, 0, 0, -1))
        self.assertTrue(in_window({"windows": {"hours": [14], "timezone": "UTC"}}, now=struct))


if __name__ == "__main__":
    unittest.main()
