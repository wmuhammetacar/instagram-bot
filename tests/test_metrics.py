import unittest

from insta_bot.db import Repo
from insta_bot.metrics import Metrics


class FakeConfig:
    def accounts(self, enabled_only=True):
        return [{"name": "a"}]

    def path(self, rel):
        return rel


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(":memory:")
        self.m = Metrics(FakeConfig(), self.repo, None)

    def test_source_conversion(self):
        # 2 hashtag takibi (1 geri-takip), 1 rakip takibi (0 geri-takip)
        self.repo.record_action("a", "follow", "1", "ok", meta={"source": "hashtag:python"})
        self.repo.record_action("a", "follow", "2", "ok", meta={"source": "hashtag:python"})
        self.repo.record_action("a", "follow", "3", "ok", meta={"source": "competitor:x"})
        self.repo.record_action("a", "followback", "1", "ok")

        data = self.m.analytics("a")
        self.assertEqual(data["totals"]["follows"], 3)
        self.assertEqual(data["totals"]["followbacks"], 1)
        self.assertAlmostEqual(data["totals"]["rate"], round(1 / 3, 3))
        self.assertEqual(data["sources"]["hashtag:python"]["follows"], 2)
        self.assertEqual(data["sources"]["hashtag:python"]["followbacks"], 1)
        self.assertEqual(data["sources"]["hashtag:python"]["rate"], 0.5)
        self.assertEqual(data["sources"]["competitor:x"]["followbacks"], 0)

    def test_no_meta_is_unknown(self):
        self.repo.record_action("a", "follow", "9", "ok")  # meta yok
        data = self.m.analytics("a")
        self.assertIn("bilinmiyor", data["sources"])
        self.assertEqual(data["sources"]["bilinmiyor"]["follows"], 1)

    def test_empty(self):
        data = self.m.analytics("a")
        self.assertEqual(data["totals"], {"follows": 0, "followbacks": 0, "rate": 0.0})
        self.assertEqual(data["sources"], {})


if __name__ == "__main__":
    unittest.main()
