import unittest

from insta_bot.targeting import TargetEngine

FILTERS = {
    "min_followers": 50,
    "max_followers": 50000,
    "max_following": 2000,
    "min_media_count": 3,
    "allow_private": False,
    "allow_verified": False,
    "last_media_max_age_days": 0,
    "bio_include": ["python"],
    "bio_exclude": ["buy"],
}


def user(pk, followers=1000, following=100, media=10, private=False, verified=False,
         bio="python developer", last_media=None):
    return {"pk": pk, "followers": followers, "following": following, "media_count": media,
            "is_private": 1 if private else 0, "is_verified": 1 if verified else 0,
            "bio": bio, "last_media_at": last_media}


class TestTargetEngine(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(TargetEngine.judge(user("1"), FILTERS, "999"), "ok")

    def test_self_excluded(self):
        self.assertEqual(TargetEngine.judge(user("999"), FILTERS, "999"), "skipped")

    def test_follower_bounds(self):
        self.assertEqual(TargetEngine.judge(user("1", followers=10), FILTERS, "999"), "skipped")
        self.assertEqual(TargetEngine.judge(user("1", followers=99999), FILTERS, "999"), "skipped")

    def test_following_bound(self):
        self.assertEqual(TargetEngine.judge(user("1", following=5000), FILTERS, "999"), "skipped")

    def test_min_media(self):
        self.assertEqual(TargetEngine.judge(user("1", media=1), FILTERS, "999"), "skipped")

    def test_private_and_verified(self):
        self.assertEqual(TargetEngine.judge(user("1", private=True), FILTERS, "999"), "skipped")
        self.assertEqual(TargetEngine.judge(user("1", verified=True), FILTERS, "999"), "skipped")

    def test_bio_filters(self):
        self.assertEqual(TargetEngine.judge(user("1", bio="i sell shoes"), FILTERS, "999"), "skipped")
        self.assertEqual(TargetEngine.judge(user("1", bio="food lover"), FILTERS, "999"), "skipped")

    def test_recency_filter(self):
        filters = dict(FILTERS, last_media_max_age_days=7)
        old = user("1", last_media="2020-01-01T10:00:00")
        self.assertEqual(TargetEngine.judge(old, filters, "999"), "skipped")
        fresh = user("2", last_media=None)
        self.assertEqual(TargetEngine.judge(fresh, filters, "999"), "ok")

    def test_scoring(self):
        scoring = {"keyword_hit": 40, "follower_balance": 30, "recency": 30}
        keyword_match = TargetEngine.score(user("1", bio="python developer",
                                                last_media="2026-08-01T10:00:00"), scoring, FILTERS)
        self.assertGreater(keyword_match, 60)
        no_keyword = TargetEngine.score(user("2", bio="nothing relevant",
                                             last_media=None), scoring, FILTERS)
        self.assertLess(no_keyword, keyword_match)


if __name__ == "__main__":
    unittest.main()
