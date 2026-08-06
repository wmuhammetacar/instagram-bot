import os
import tempfile
import unittest
from pathlib import Path

from insta_bot.config import Config

GLOBAL_YAML = """
limits: {follows: 5, likes: 5, comments: 2, dms: 2, posts: 2, hourly_cap_fraction: 0.5}
delays: {base: [1, 2], spread: [0, 1], min: 0.01}
targeting:
  default_budget_per_run: 5
  filters: {min_followers: 1, max_followers: 100, max_following: 1000, min_media_count: 0}
comments: {rotation: ["hi {username}"]}
dm: {rotation: ["hi {username}"]}
"""

ACCOUNTS_YAML = """
accounts:
  - name: a
    username: u
    password_env: IG_PW_A
    enabled: true
"""


class TestEnvParsing(unittest.TestCase):
    def _load(self, env_text):
        base = Path(tempfile.mkdtemp())
        (base / "config.yaml").write_text(GLOBAL_YAML, encoding="utf-8")
        (base / "accounts.yaml").write_text(ACCOUNTS_YAML, encoding="utf-8")
        (base / ".env").write_text(env_text, encoding="utf-8")
        return Config(base)

    def _clean(self, *keys):
        for k in keys:
            os.environ.pop(k, None)

    def test_strips_surrounding_quotes(self):
        self._clean("IG_PW_A")
        cfg = self._load('IG_PW_A="gizli sifre"\n')
        self.assertEqual(cfg.account("a")["password"], "gizli sifre")
        self._clean("IG_PW_A")

    def test_strips_single_quotes(self):
        self._clean("IG_PW_A")
        cfg = self._load("IG_PW_A='abc'\n")
        self.assertEqual(cfg.account("a")["password"], "abc")
        self._clean("IG_PW_A")

    def test_handles_export_prefix(self):
        self._clean("IG_PW_A")
        cfg = self._load("export IG_PW_A=plainpass\n")
        self.assertEqual(cfg.account("a")["password"], "plainpass")
        self._clean("IG_PW_A")

    def test_ignores_comments_and_blanks(self):
        self._clean("IG_PW_A")
        cfg = self._load("# yorum\n\nIG_PW_A=xyz\n")
        self.assertEqual(cfg.account("a")["password"], "xyz")
        self._clean("IG_PW_A")


if __name__ == "__main__":
    unittest.main()
