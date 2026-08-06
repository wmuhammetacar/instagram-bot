import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # httpx kurulu degilse TestClient import edilemez
    HAVE_CLIENT = False

from insta_bot.config import Config
from insta_bot.db import Repo

CONFIG_YAML = """
system:
  timezone: "Europe/Istanbul"
  dashboard_token: "__TOKEN__"
limits:
  follows: 5
  likes: 5
  comments: 2
  dms: 2
  posts: 2
  hourly_cap_fraction: 0.5
delays:
  base: [1, 2]
  spread: [0, 1]
  min: 0.01
targeting:
  default_budget_per_run: 5
  sources: {hashtags: [], competitors: []}
  filters: {min_followers: 1, max_followers: 100, max_following: 1000, min_media_count: 0}
comments:
  rotation: ["hi {username}"]
dm:
  rotation: ["hi {username}"]
"""

ACCOUNTS_YAML = """
accounts:
  - name: a
    username: u
    password: x
    enabled: true
    windows: {}
"""


@unittest.skipUnless(HAVE_CLIENT, "fastapi TestClient icin httpx gerekli")
class TestApiAuth(unittest.TestCase):
    def _client(self, token):
        from insta_bot.api import create_app
        base = Path(tempfile.mkdtemp())
        (base / "config.yaml").write_text(CONFIG_YAML.replace("__TOKEN__", token), encoding="utf-8")
        (base / "accounts.yaml").write_text(ACCOUNTS_YAML, encoding="utf-8")
        return TestClient(create_app(Config(base), Repo(":memory:")))

    def test_get_endpoints_open(self):
        # Salt-okunur uclar token'dan bagimsiz acik.
        c = self._client("secret")
        self.assertEqual(c.get("/api/status").status_code, 200)
        self.assertEqual(c.get("/api/targets").status_code, 200)

    def test_mutating_blocked_without_token(self):
        c = self._client("secret")
        r = c.post("/api/targets/clear", json={"status": "processed"})
        self.assertEqual(r.status_code, 401)

    def test_mutating_blocked_with_wrong_token(self):
        c = self._client("secret")
        r = c.post("/api/targets/clear", json={"status": "processed"},
                   headers={"X-Auth-Token": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_mutating_allowed_with_token(self):
        c = self._client("secret")
        r = c.post("/api/targets/clear", json={"status": "processed"},
                   headers={"X-Auth-Token": "secret"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("cleared"))

    def test_no_token_configured_leaves_open(self):
        # Token bos ise koruma devrede degil (geriye donuk uyumluluk).
        c = self._client("")
        r = c.post("/api/targets/clear", json={"status": "processed"})
        self.assertNotEqual(r.status_code, 401)

    def test_status_exposes_unfollow_keys(self):
        # Panel metresi ve raporu icin unfollows anahtari hem today hem limits'te olmali.
        c = self._client("secret")
        acc = c.get("/api/status").json()["accounts"][0]
        self.assertIn("unfollows", acc["today"])
        self.assertIn("unfollows", acc["limits"])
        self.assertGreater(acc["limits"]["unfollows"], 0)  # follows'tan turetilir

    def test_unfollow_requires_token(self):
        c = self._client("secret")
        r = c.post("/api/unfollow", json={"account": "a"})
        self.assertEqual(r.status_code, 401)

    def test_unfollow_unknown_account_404(self):
        c = self._client("secret")
        r = c.post("/api/unfollow", json={"account": "yok"},
                   headers={"X-Auth-Token": "secret"})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
