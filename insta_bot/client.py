import os
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired, TwoFactorRequired


class ClientManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        client_cfg = config.get("client", {})
        self.username = client_cfg.get("username") or os.getenv("IG_USERNAME", "")
        self.password = client_cfg.get("password") or os.getenv("IG_PASSWORD", "")
        self.session_file = Path(client_cfg.get("session_file", "data/session.json"))
        self.timeout = int(client_cfg.get("request_timeout", 30))
        self.client = None

    def login(self, force=False):
        if not self.username or not self.password:
            raise ValueError("Kullanici adi/sifre eksik. config.yaml veya .env dosyasini doldur.")
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        if self.session_file.exists() and not force:
            try:
                self.client = self._session_login()
                return self.client
            except (LoginRequired, ClientError) as exc:
                self.logger.warning(f"Kayitli oturum gecersiz, yeniden giriliyor: {exc}")
        self.client = self._fresh_login()
        self.client.dump_settings(self.session_file)
        self.logger.info("Oturum kaydedildi")
        return self.client

    def _session_login(self):
        cl = self._new_client()
        cl.load_settings(self.session_file)
        cl.login(self.username, self.password)
        self.logger.info("Kayitli oturumla giris yapildi")
        return cl

    def _fresh_login(self):
        cl = self._new_client()
        try:
            cl.login(self.username, self.password)
        except TwoFactorRequired:
            code = input("2FA dogrulama kodu: ").strip()
            cl.login(self.username, self.password, verification_code=code)
        self.logger.info(f"Giris basarili: {self.username}")
        return cl

    def _new_client(self):
        cl = Client()
        cl.request_timeout = self.timeout
        return cl
