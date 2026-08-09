import logging

import requests

LOGGER = logging.getLogger("insta_bot.notify")


class Notifier:
    """Operasyonel bildirim gonderici (Telegram / Discord / genel webhook).

    config.yaml:
      notifications:
        enabled: true
        events: ["challenge", "restriction", "error"]   # bos ise tumu
        telegram: { bot_token: "...", chat_id: "..." }
        discord:  { webhook_url: "https://discord.com/api/webhooks/..." }
        webhook:  { url: "https://...", }

    Sifreler/anahtarlar ortam degiskeninden de okunabilir:
      IG_TG_BOT_TOKEN, IG_TG_CHAT_ID, IG_DISCORD_WEBHOOK, IG_WEBHOOK_URL
    Baglanti hatalari yutulur; bildirim hicbir zaman ana akisi durdurmaz.
    """

    def __init__(self, config, logger=None):
        self.logger = logger or LOGGER
        self._cfg = (config.get("notifications", {}) if config else {}) or {}
        self.enabled = bool(self._cfg.get("enabled", False))
        events = self._cfg.get("events") or []
        self.events = {str(e).lower() for e in events}
        self.timeout = int(self._cfg.get("timeout", 10))
        import os
        self._env = os.environ

    def _wants(self, event):
        if not self.enabled:
            return False
        return not self.events or str(event).lower() in self.events

    def notify(self, event, message):
        """event: challenge|restriction|error|info ; message: metin."""
        if not self._wants(event):
            return False
        text = f"[instagram-bot] {event.upper()}: {message}"
        sent = False
        sent |= self._telegram(text)
        sent |= self._discord(text)
        sent |= self._webhook(event, message, text)
        return sent

    def _telegram(self, text):
        tg = self._cfg.get("telegram") or {}
        token = tg.get("bot_token") or self._env.get("IG_TG_BOT_TOKEN")
        chat_id = tg.get("chat_id") or self._env.get("IG_TG_CHAT_ID")
        if not token or not chat_id:
            return False
        return self._post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text})

    def _discord(self, text):
        dc = self._cfg.get("discord") or {}
        url = dc.get("webhook_url") or self._env.get("IG_DISCORD_WEBHOOK")
        if not url:
            return False
        return self._post(url, json={"content": text})

    def _webhook(self, event, message, text):
        wh = self._cfg.get("webhook") or {}
        url = wh.get("url") or self._env.get("IG_WEBHOOK_URL")
        if not url:
            return False
        return self._post(url, json={"event": event, "message": message, "text": text})

    def _post(self, url, json=None):
        try:
            resp = requests.post(url, json=json, timeout=self.timeout)
            if resp.status_code >= 400:
                self.logger.warning(f"Bildirim basarisiz ({resp.status_code}): {url.split('/')[2]}")
                return False
            return True
        except requests.RequestException as exc:
            self.logger.warning(f"Bildirim gonderilemedi: {exc}")
            return False
