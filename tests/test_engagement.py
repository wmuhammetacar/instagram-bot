import tempfile
import unittest
from datetime import datetime, timezone
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
        if fn in ("media_like", "user_follow", "media_comment", "direct_send",
                  "user_info"):
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

    def test_dm_dedupe(self):
        self.runner.dm(self.client, "testacc", usernames=["ali", "ali"])
        self.assertEqual(self.repo.daily_limit("testacc", "dms",
                                               datetime.now().strftime("%Y-%m-%d")), 1)

    def test_dm_limit(self):
        self.repo.bump_limit("testacc", "dms", datetime.now().strftime("%Y-%m-%d"), 0)
        summary = self.runner.dm(self.client, "testacc", usernames=["a", "b"])
        self.assertEqual(summary["dms"], 0)


if __name__ == "__main__":
    unittest.main()
