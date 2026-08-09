import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from instagrapi.exceptions import ClientError, UserNotFound

from insta_bot.config import Config
from insta_bot.db import Repo
from insta_bot.engagement import Runner

CONFIG_YAML = """
system:
  timezone: "Europe/Istanbul"
limits:
  follows: 2
  likes: 2
  comments: 1
  dms: 1
  posts: 2
  hourly_cap_fraction: 0.5
delays:
  base: [1, 2]
  spread: [0, 1]
  min: 0.01
  heat_multiplier: 0
  after_error: 1
targeting:
  default_budget_per_run: 10
  sources:
    hashtags: ["test"]
    competitors: []
  filters:
    min_followers: 5
    max_followers: 100000
    max_following: 10000
    min_media_count: 1
    allow_private: false
    allow_verified: false
    last_media_max_age_days: 0
    bio_include: []
    bio_exclude: []
  scoring:
    keyword_hit: 40
    follower_balance: 30
    recency: 30
comments:
  rotation: ["harika {username}!"]
dm:
  rotation: ["selam {username}"]
posting:
  rotation: []
  hashtag_bank: {}
  hashtags_per_post: 0
"""

ACCOUNTS_YAML = """
accounts:
  - name: testacc
    username: test_user
    password: x
    enabled: true
    windows: {}
"""


def make_media(pk, user):
    return SimpleNamespace(pk=str(pk), taken_at=datetime.now(timezone.utc), user=user)


def make_user(pk, username, followers=1000, media=10):
    return SimpleNamespace(
        pk=str(pk), username=username, full_name=username, biography="bio",
        follower_count=followers, following_count=100, media_count=media,
        is_private=False, is_verified=False)


class FakeClient:
    user_id = "999"
    username = "test_user"

    def __init__(self):
        self.medias_by_user = {}
        self.hashtag_medias = []
        self.calls = []
        self.call_errors = {}
        self.friendships = {}

    def call(self, fn, *args, **kw):
        self.calls.append((fn, args))
        error = self.call_errors.get(fn)
        if error:
            raise error("fake")
        if fn == "hashtag_medias_recent":
            return self.hashtag_medias
        if fn == "user_id_from_username":
            return "100"
        if fn == "user_followers":
            return {}
        if fn == "user_medias":
            return self.medias_by_user.get(args[0], [])
        if fn == "user_friendship":
            return self.friendships.get(args[0])
        if fn in ("media_like", "user_follow", "user_unfollow", "media_comment",
                  "direct_send", "user_info"):
            return True
        return None


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        (base / "accounts.yaml").write_text(ACCOUNTS_YAML, encoding="utf-8")
        self.config = Config(base)
        self.repo = Repo(":memory:")
        self.runner = Runner(self.config, self.repo, None, dry_run=False)
        self.runner.logger = type("L", (), {"info": lambda *a, **k: None,
                                            "warning": lambda *a, **k: None,
                                            "error": lambda *a, **k: None})()
        self.client = FakeClient()
        users = [make_user(1, "ali"), make_user(2, "veli"), make_user(3, "can")]
        self.client.hashtag_medias = [make_media(f"m{i}", u) for i, u in enumerate(users)]
        for u in users:
            self.client.medias_by_user[u.pk] = [make_media(f"m{u.pk}", u)]
        self.delay_patch = patch("insta_bot.security.DelayEngine.pause")
        self.delay_patch.start()
        self.addCleanup(self.delay_patch.stop)

    def test_engage_respects_limits(self):
        summary = self.runner.engage(self.client, "testacc", hashtags=["test"],
                                     budget=10, like=True, comment=False)
        self.assertEqual(summary["likes"], 2)
        self.assertEqual(summary["follows"], 2)
        self.assertEqual(self.repo.daily_limit("testacc", "likes", None), 2)
        date = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(self.repo.daily_limit("testacc", "likes", date), 2)

    def test_follow_records_source_meta(self):
        # Takip aksiyonu hedef kaynagini meta'ya yazmali (kaynak analitigi icin).
        self.runner.engage(self.client, "testacc", hashtags=["test"], budget=1,
                           like=False, comment=False)
        rows = self.repo.actions_by_type("testacc", "follow")
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["meta"])
        self.assertIn("source", rows[0]["meta"])

    def test_second_run_skips_processed(self):
        self.runner.engage(self.client, "testacc", hashtags=["test"], budget=10)
        self.client.calls.clear()
        summary = self.runner.engage(self.client, "testacc", hashtags=["test"], budget=10)
        self.assertEqual(summary["likes"], 0)
        self.assertEqual(summary["follows"], 0)

    def test_dry_run_no_side_effects(self):
        runner = Runner(self.config, self.repo, None, dry_run=True)
        runner.logger = self.runner.logger
        summary = runner.engage(self.client, "testacc", hashtags=["test"], budget=10)
        self.assertEqual(summary["likes"], 3)
        self.assertEqual(summary["follows"], 3)
        date = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(self.repo.daily_limit("testacc", "likes", date), 0)
        self.assertEqual(self.repo.processed_set("testacc", "like"), set())

    def test_comment_uses_rotation(self):
        summary = self.runner.engage(self.client, "testacc", hashtags=["test"],
                                     budget=10, like=True, comment=True)
        self.assertEqual(summary["comments"], 1)

    def test_target_error_skips(self):
        self.client.call_errors["user_follow"] = UserNotFound
        summary = self.runner.engage(self.client, "testacc", hashtags=["test"], budget=10)
        self.assertEqual(summary["follows"], 0)
        self.assertGreaterEqual(summary["errors"], 1)

    def test_restriction_sets_cooldown(self):
        self.client.call_errors["user_follow"] = lambda *a: ClientError(
            "action blocked: too many requests")
        self.runner.engage(self.client, "testacc", hashtags=["test"], budget=10)
        self.assertIn("restriction", self.repo.active_cooldowns("testacc"))

    def test_like_restriction_sets_cooldown(self):
        # Regresyon: beğeni sırasinda kisit gelince cooldown kurulmali, cokmemeli
        # (onceden media_like cagrisina cooldowns gecilmedigi icin AttributeError atiyordu).
        self.client.call_errors["media_like"] = lambda *a: ClientError(
            "action blocked: too many requests")
        self.runner.engage(self.client, "testacc", hashtags=["test"],
                           budget=10, like=True, comment=False)
        self.assertIn("restriction", self.repo.active_cooldowns("testacc"))

    def test_media_fetched_once_per_target(self):
        # Regresyon: begeni + yorum ayni gonderiyi kullanir; user_medias hedef basina
        # bir kez cagrilmali (onceden iki kez cagriliyordu).
        u = make_user(1, "solo")
        self.client.hashtag_medias = [make_media("m0", u)]
        self.client.medias_by_user = {u.pk: [make_media("mm", u)]}
        self.runner.engage(self.client, "testacc", hashtags=["test"],
                           budget=10, like=True, comment=True)
        um_calls = [c for c in self.client.calls if c[0] == "user_medias"]
        self.assertEqual(len(um_calls), 1)

    def test_humanize_views_profile_before_follow(self):
        # humanize acikken takipten once user_info cagrilmali (insansi gezinme).
        base = Path(self.tmp.name)
        cfg_text = CONFIG_YAML + "\nhumanize:\n  enabled: true\n  view_profile_prob: 1.0\n  view_pause: [0, 0]\n"
        (base / "config.yaml").write_text(cfg_text, encoding="utf-8")
        config = Config(base)
        runner = Runner(config, self.repo, self.runner.logger, dry_run=False)
        with patch("insta_bot.engagement.time.sleep", return_value=None):
            runner.engage(self.client, "testacc", hashtags=["test"], budget=1,
                          like=False, comment=False)
        self.assertIn("user_info", [c[0] for c in self.client.calls])

    def test_humanize_disabled_no_user_info(self):
        # Varsayilan (humanize kapali) -> user_info cagrilmaz.
        self.runner.engage(self.client, "testacc", hashtags=["test"], budget=1,
                           like=False, comment=False)
        self.assertNotIn("user_info", [c[0] for c in self.client.calls])

    def test_dm_dedupe(self):
        self.runner.dm(self.client, "testacc", usernames=["ali", "ali"])
        self.assertEqual(self.repo.daily_limit("testacc", "dms",
                                               datetime.now().strftime("%Y-%m-%d")), 1)

    def test_dm_limit(self):
        self.repo.bump_limit("testacc", "dms", datetime.now().strftime("%Y-%m-%d"), 0)
        summary = self.runner.dm(self.client, "testacc", usernames=["a", "b"])
        self.assertEqual(summary["dms"], 0)


class TestUnfollow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        (base / "accounts.yaml").write_text(ACCOUNTS_YAML, encoding="utf-8")
        self.config = Config(base)
        self.repo = Repo(":memory:")
        self.runner = Runner(self.config, self.repo, None, dry_run=False)
        self.runner.logger = type("L", (), {"info": lambda *a, **k: None,
                                            "warning": lambda *a, **k: None,
                                            "error": lambda *a, **k: None})()
        self.client = FakeClient()
        self.delay_patch = patch("insta_bot.security.DelayEngine.pause")
        self.delay_patch.start()
        self.addCleanup(self.delay_patch.stop)

    def _seed_follow(self, pk, days_ago):
        ts = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        self.repo._exec(
            "INSERT INTO actions (account, action_type, target, status, created_at) "
            "VALUES ('testacc','follow',?, 'ok', ?)", (str(pk), ts))

    def test_unfollows_old_non_followers(self):
        self._seed_follow("11", days_ago=10)
        self._seed_follow("22", days_ago=1)  # bekleme suresi dolmadi
        summary = self.runner.unfollow(self.client, "testacc", grace_days=3, keep_followers=False)
        self.assertEqual(summary["unfollows"], 1)
        unfollowed = [c for c in self.client.calls if c[0] == "user_unfollow"]
        self.assertEqual(unfollowed, [("user_unfollow", ("11",))])

    def test_keeps_followers_back(self):
        self._seed_follow("11", days_ago=10)
        self.client.friendships["11"] = SimpleNamespace(followed_by=True)
        summary = self.runner.unfollow(self.client, "testacc", grace_days=3, keep_followers=True)
        self.assertEqual(summary["unfollows"], 0)
        self.assertEqual(summary["kept"], 1)

    def test_keep_records_followback(self):
        # Geri takip tespit edilince donusum analitigi icin 'followback' kaydedilmeli.
        self._seed_follow("11", days_ago=10)
        self.client.friendships["11"] = SimpleNamespace(followed_by=True)
        self.runner.unfollow(self.client, "testacc", grace_days=3, keep_followers=True)
        self.assertTrue(self.repo.is_processed("testacc", "followback", "11"))
        rows = self.repo.actions_by_type("testacc", "followback")
        self.assertEqual(len(rows), 1)

    def test_not_reprocessed_after_unfollow(self):
        self._seed_follow("11", days_ago=10)
        self.runner.unfollow(self.client, "testacc", grace_days=3, keep_followers=False)
        self.client.calls.clear()
        summary = self.runner.unfollow(self.client, "testacc", grace_days=3, keep_followers=False)
        self.assertEqual(summary["unfollows"], 0)

    def test_respects_budget(self):
        for i in range(5):
            self._seed_follow(str(100 + i), days_ago=10)
        summary = self.runner.unfollow(self.client, "testacc", budget=2, grace_days=3, keep_followers=False)
        self.assertEqual(summary["unfollows"], 2)


if __name__ == "__main__":
    unittest.main()
