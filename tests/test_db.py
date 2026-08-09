import unittest

from insta_bot.db import Repo


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(":memory:")

    def test_targets_upsert_and_status(self):
        rows = [
            {"pk": "1", "username": "ali", "followers": 100, "following": 50,
             "media_count": 10, "is_private": 0, "is_verified": 0, "score": 70.0,
             "source": "hashtag:python"},
            {"pk": "2", "username": "veli", "followers": 200, "following": 60,
             "media_count": 5, "is_private": 0, "is_verified": 0, "score": 40.0,
             "source": "hashtag:python"},
        ]
        res = self.repo.upsert_targets("acc", rows)
        self.assertEqual(res["added"], 2)
        self.assertEqual(self.repo.targets_count(status="pending"), 2)
        self.repo.set_target_status("acc", "1", "processed")
        self.assertEqual(self.repo.targets_count(status="processed"), 1)
        pending = self.repo.pending_targets("acc", limit=5)
        self.assertEqual([t["pk"] for t in pending], ["2"])
        res2 = self.repo.upsert_targets("acc", [dict(rows[0], score=90.0)])
        self.assertEqual(res2["added"], 0)
        self.repo.set_target_status("acc", "1", "processed")
        self.assertEqual(self.repo.targets_count(status="processed"), 1)

    def test_processed_unique(self):
        self.repo.mark_processed("a", "follow", "5")
        self.repo.mark_processed("a", "follow", "5")
        self.repo.mark_processed("a", "follow", "6")
        self.assertEqual(self.repo.processed_set("a", "follow"), {"5", "6"})
        self.assertTrue(self.repo.is_processed("a", "follow", "5"))
        self.assertFalse(self.repo.is_processed("a", "like", "5"))

    def test_actions(self):
        self.repo.record_action("a", "follow", "1", "ok")
        self.repo.record_action("a", "follow", "2", "fail", "hata")
        stats = self.repo.action_stats("a")
        by_status = {(r["action_type"], r["status"]): r["c"] for r in stats}
        self.assertEqual(by_status[("follow", "ok")], 1)
        self.assertEqual(by_status[("follow", "fail")], 1)
        self.assertEqual(len(self.repo.recent_actions("a")), 2)

    def test_hourly_actions_from_created_at(self):
        # created_at'ten saat turetilir; yalnizca 'ok' sayilir, 24 elemanli seri doner.
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            "VALUES ('a','like','1','ok','2026-08-06 09:15:00')")
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            "VALUES ('a','like','2','ok','2026-08-06 09:40:00')")
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            "VALUES ('a','like','3','fail','2026-08-06 09:50:00')")
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            "VALUES ('a','like','4','ok','2026-08-06 14:00:00')")
        series = self.repo.hourly_actions("a", "2026-08-06", "like")
        self.assertEqual(len(series), 24)
        self.assertEqual(series[9], 2)
        self.assertEqual(series[14], 1)
        self.assertEqual(sum(series), 3)

    def test_actions_by_type_with_meta(self):
        self.repo.record_action("a", "follow", "1", "ok", meta={"source": "hashtag:python"})
        self.repo.record_action("a", "follow", "2", "ok")
        self.repo.record_action("a", "like", "3", "ok")
        rows = self.repo.actions_by_type("a", "follow")
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r["meta"] and "python" in r["meta"] for r in rows))

    def test_hourly_series_normalizes_plural(self):
        # Regresyon: panel/metrics cogul ('follows') gonderir, actions tekil ('follow')
        # saklar; hourly_series normalize etmezse hep 0 doner.
        import time as _t

        from insta_bot.metrics import Metrics
        hour = int(_t.strftime("%H"))
        date = _t.strftime("%Y-%m-%d")
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            f"VALUES ('a','follow','1','ok','{date} {hour:02d}:30:00')")

        class Cfg:
            def accounts(self):
                return [{"name": "a"}]

        m = Metrics(Cfg(), self.repo, None)
        self.assertEqual(sum(m.hourly_series("a", action_type="follows")), 1)  # cogul
        self.assertEqual(sum(m.hourly_series("a", action_type="follow")), 1)   # tekil de calisir

    def test_limits(self):
        self.repo.bump_limit("a", "follows", "2026-08-05", 10)
        self.repo.bump_limit("a", "follows", "2026-08-05", 10)
        self.repo.bump_limit("a", "follows", "2026-08-05", 11)
        self.assertEqual(self.repo.daily_limit("a", "follows", "2026-08-05"), 3)
        self.assertEqual(self.repo.hour_limit("a", "follows", "2026-08-05", 10), 2)
        self.assertEqual(self.repo.today_limits("a", "2026-08-05")["follows"], 3)

    def test_cooldown_and_state(self):
        self.repo.set_cooldown("a", "restriction", 10**10, "kisit")
        self.assertIn("restriction", self.repo.active_cooldowns("a"))
        self.repo.set_state("a", needs_challenge=1)
        self.assertEqual(self.repo.state("a")["needs_challenge"], 1)

    def test_tasks(self):
        tid = self.repo.add_task("g1", "a", "engage", {"budget": 5}, {"every_hours": 4})
        tasks = self.repo.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], tid)
        self.repo.update_task(tid, next_run="x")
        self.assertEqual(self.repo.list_tasks()[0]["next_run"], "x")
        self.repo.delete_task(tid)
        self.assertEqual(self.repo.list_tasks(), [])


if __name__ == "__main__":
    unittest.main()
