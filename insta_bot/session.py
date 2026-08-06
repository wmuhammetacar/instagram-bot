import sys
import time
from pathlib import Path

import requests
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    ClientThrottledError,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    TwoFactorRequired,
)

TRANSIENT = (PleaseWaitFewMinutes, RateLimitError, ClientThrottledError)


class AccountError(Exception):
    pass


class ChallengePending(AccountError):
    pass


class BotClient:
    def __init__(self, config, repo, logger, account_cfg):
        self.config = config
        self.repo = repo
        self.logger = logger
        self.account = account_cfg
        self.name = account_cfg["name"]
        self.username = account_cfg["username"]
        self.password = account_cfg["password"]
        self.proxy = account_cfg.get("proxy") or ""
        self.session_dir = Path(config.path(config.get("system", {}).get("session_dir", "data/sessions"))) / self.name
        self.session_file = self.session_dir / "session.json"
        self.cl = None
        self.connected_at = None

    def connect(self, force=False, challenge_callback=None, verification_callback=None):
        if not self.username or not self.password:
            raise AccountError(f"[{self.name}] Kullanici adi/sifre eksik (accounts.yaml / .env kontrol et)")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        cl = Client()
        cl.request_timeout = int(self.config.get("system", {}).get("request_timeout", 60))
        if self.proxy:
            try:
                cl.set_proxy(self.proxy)
                self.logger.info(f"[{self.name}] Proxy aktif: {self.proxy.split('@')[-1]}")
            except Exception as exc:
                self.logger.error(f"[{self.name}] Proxy ayarlanamadi: {exc}")
        cl.challenge_code_handler = lambda u, c: self._challenge_code(u, c, challenge_callback)
        if self.session_file.exists() and not force:
            try:
                cl.load_settings(self.session_file)
                cl.login(self.username, self.password)
                return self._finish(cl)
            except LoginRequired:
                self.logger.warning(f"[{self.name}] Kayitli oturum gecersiz, yeniden giriliyor")
            except ChallengeRequired:
                raise ChallengePending(f"[{self.name}] Challenge dogrulamasi gerekiyor")
        cl = self._fresh_login(cl, verification_callback)
        cl.dump_settings(self.session_file)
        return self._finish(cl)

    def _fresh_login(self, cl, verification_callback):
        try:
            cl.login(self.username, self.password)
        except TwoFactorRequired:
            code = self._ask("2FA dogrulama kodu", verification_callback)
            cl.login(self.username, self.password, verification_code=code)
        except ChallengeRequired:
            self.repo.set_state(self.name, needs_challenge=1, last_error="challenge")
            raise ChallengePending(
                f"[{self.name}] Instagram challenge istedi. Terminalde 'python bot.py login {self.name}' calistir.")
        return cl

    def _finish(self, cl):
        self.cl = cl
        self.connected_at = time.time()
        self.repo.set_state(self.name, needs_challenge=0, last_login=time.strftime("%Y-%m-%d %H:%M:%S"))
        self.logger.info(f"[{self.name}] Baglanti hazir (uid={cl.user_id})")
        return self

    def _challenge_code(self, username, choice, callback):
        self.repo.set_state(self.name, needs_challenge=1, last_error=f"challenge:{choice}")
        if callback:
            return callback(username, choice)
        if sys.stdin.isatty():
            self.logger.warning(f"[{self.name}] Challenge (kanal: {choice}). Dogrulama kodunu girin:")
            return input("Instagram kodu: ").strip()
        raise ChallengeRequired(f"[{self.name}] Challenge cozumlenemedi (interaktif degil)")

    def _ask(self, label, callback):
        if callback:
            return callback()
        if sys.stdin.isatty():
            return input(f"{label}: ").strip()
        raise AccountError(f"[{self.name}] {label} gerekli ama terminal interaktif degil")

    def call(self, fn, *args, retries=2, **kwargs):
        last = None
        for attempt in range(retries + 1):
            try:
                return getattr(self.cl, fn)(*args, **kwargs)
            except TRANSIENT as exc:
                wait = int(getattr(exc, "wait_seconds", 0)) or (600 if attempt == 0 else 900)
                self.logger.warning(f"[{self.name}] {type(exc).__name__}, {wait} sn bekleniyor")
                time.sleep(wait)
            except LoginRequired:
                self.logger.warning(f"[{self.name}] Oturum dusmus, yeniden giris deneniyor")
                self.connect(force=True)
            except (requests.RequestException, TimeoutError, OSError) as exc:
                self.logger.warning(f"[{self.name}] Ag hatasi ({type(exc).__name__}), tekrar deneniyor")
                time.sleep(15 * (attempt + 1))
            except ClientError as exc:
                raise
            last = exc
        raise AccountError(f"[{self.name}] {fn} islemi {retries + 1} denemede basarisiz: {last}")
