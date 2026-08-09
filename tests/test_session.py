import unittest
from unittest.mock import MagicMock, patch

from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes

from insta_bot.session import AccountError, BotClient


def _make_client():
    # __init__'i atlayarak yalnizca call() davranisini test edelim.
    c = BotClient.__new__(BotClient)
    c.name = "acc"
    c.logger = type("L", (), {"warning": lambda *a, **k: None,
                              "info": lambda *a, **k: None,
                              "error": lambda *a, **k: None})()
    return c


class FakeCl:
    def __init__(self, seq):
        self._seq = list(seq)
        self.calls = 0

    def op(self, *a, **k):
        self.calls += 1
        item = self._seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeConfig:
    def __init__(self, system):
        self._sys = system

    def get(self, key, default=None):
        return self._sys if key == "system" else default


def _proxy_client(system, proxy="http://user:pass@1.2.3.4:8080"):
    c = BotClient.__new__(BotClient)
    c.name = "acc"
    c.proxy = proxy
    c.config = FakeConfig(system)
    c.logger = type("L", (), {"warning": lambda *a, **k: None,
                              "info": lambda *a, **k: None,
                              "error": lambda *a, **k: None})()
    return c


class TestProxyCheck(unittest.TestCase):
    def test_disabled_skips(self):
        c = _proxy_client({"proxy_check": False})
        with patch("insta_bot.session.requests.get") as get:
            c._check_proxy()
            get.assert_not_called()

    def test_success_logs_ip(self):
        c = _proxy_client({"proxy_check": True})
        with patch("insta_bot.session.requests.get") as get:
            get.return_value = MagicMock(
                headers={"content-type": "application/json"},
                status_code=200)
            get.return_value.json.return_value = {"ip": "9.9.9.9"}
            get.return_value.raise_for_status = lambda: None
            c._check_proxy()  # patlamamali
            get.assert_called_once()

    def test_failure_required_raises(self):
        import requests
        c = _proxy_client({"proxy_check": True, "proxy_required": True})
        with patch("insta_bot.session.requests.get", side_effect=requests.RequestException("down")), \
                self.assertRaises(AccountError):
            c._check_proxy()

    def test_failure_not_required_warns(self):
        import requests
        c = _proxy_client({"proxy_check": True, "proxy_required": False})
        with patch("insta_bot.session.requests.get", side_effect=requests.RequestException("down")):
            c._check_proxy()  # patlamamali


class TestCallRetry(unittest.TestCase):
    def test_transient_then_success(self):
        # Ilk cagri gecici hata, ikincisi basarili -> retry calismali (UnboundLocalError degil).
        client = _make_client()
        client.cl = FakeCl([PleaseWaitFewMinutes("bekle"), "ok"])
        with patch("insta_bot.session.time.sleep", return_value=None):
            result = client.call("op", retries=2)
        self.assertEqual(result, "ok")
        self.assertEqual(client.cl.calls, 2)

    def test_exhausted_raises_accounterror(self):
        # Tum denemeler gecici hata -> temiz AccountError (son hata mesajiyla).
        client = _make_client()
        client.cl = FakeCl([PleaseWaitFewMinutes("x")] * 3)
        with patch("insta_bot.session.time.sleep", return_value=None), \
                self.assertRaises(AccountError) as ctx:
            client.call("op", retries=2)
        self.assertIn("op", str(ctx.exception))
        self.assertEqual(client.cl.calls, 3)

    def test_clienterror_propagates_immediately(self):
        client = _make_client()
        client.cl = FakeCl([ClientError("kalici")])
        with self.assertRaises(ClientError):
            client.call("op", retries=2)
        self.assertEqual(client.cl.calls, 1)


if __name__ == "__main__":
    unittest.main()
