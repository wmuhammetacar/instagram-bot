import unittest
from unittest.mock import MagicMock, patch


class FakeConfig:
    def __init__(self, notifications):
        self._n = notifications

    def get(self, key, default=None):
        if key == "notifications":
            return self._n
        return default


def _import():
    from insta_bot.notify import Notifier
    return Notifier


class TestNotifier(unittest.TestCase):
    def test_disabled_sends_nothing(self):
        Notifier = _import()
        n = Notifier(FakeConfig({"enabled": False, "telegram": {"bot_token": "t", "chat_id": "c"}}))
        with patch("insta_bot.notify.requests.post") as post:
            self.assertFalse(n.notify("challenge", "test"))
            post.assert_not_called()

    def test_event_filter(self):
        Notifier = _import()
        cfg = FakeConfig({"enabled": True, "events": ["challenge"],
                          "discord": {"webhook_url": "https://x/y/z"}})
        n = Notifier(cfg)
        with patch("insta_bot.notify.requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            self.assertTrue(n.notify("challenge", "a"))
            self.assertFalse(n.notify("restriction", "b"))  # filtre disinda
            self.assertEqual(post.call_count, 1)

    def test_telegram_and_discord_payloads(self):
        Notifier = _import()
        cfg = FakeConfig({"enabled": True,
                          "telegram": {"bot_token": "TOK", "chat_id": "42"},
                          "discord": {"webhook_url": "https://discord/webhook"}})
        n = Notifier(cfg)
        with patch("insta_bot.notify.requests.post") as post:
            post.return_value = MagicMock(status_code=204)
            self.assertTrue(n.notify("restriction", "kisit var"))
            urls = [c.args[0] for c in post.call_args_list]
            self.assertTrue(any("api.telegram.org/botTOK" in u for u in urls))
            self.assertIn("https://discord/webhook", urls)

    def test_network_error_swallowed(self):
        import requests
        Notifier = _import()
        cfg = FakeConfig({"enabled": True, "webhook": {"url": "https://x"}})
        n = Notifier(cfg)
        with patch("insta_bot.notify.requests.post", side_effect=requests.RequestException("down")):
            self.assertFalse(n.notify("error", "boom"))  # cokmeden False

    def test_env_fallback(self):
        import os
        Notifier = _import()
        cfg = FakeConfig({"enabled": True})
        os.environ["IG_DISCORD_WEBHOOK"] = "https://env/webhook"
        try:
            n = Notifier(cfg)
            with patch("insta_bot.notify.requests.post") as post:
                post.return_value = MagicMock(status_code=200)
                self.assertTrue(n.notify("challenge", "x"))
                self.assertEqual(post.call_args_list[0].args[0], "https://env/webhook")
        finally:
            os.environ.pop("IG_DISCORD_WEBHOOK", None)


if __name__ == "__main__":
    unittest.main()
