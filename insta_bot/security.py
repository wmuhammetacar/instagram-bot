import logging
import random
import time

LOGGER = logging.getLogger("insta_bot")

ACTION_TYPES = ("follows", "unfollows", "likes", "comments", "dms", "posts")


class DelayEngine:
    """Insan benzeri bekleme: taban + varyans + isinma carpani + hata sonrasi yavaslatma."""

    def __init__(self, cfg):
        delays = cfg.get("delays", {})
        self.base = list(delays.get("base", [45, 120]))
        self.spread = list(delays.get("spread", [10, 60]))
        self.actions = {k: list(v) for k, v in delays.get("actions", {}).items()}
        self.heat_multiplier = float(delays.get("heat_multiplier", 2.0))
        self.heat_after = int(delays.get("heat_after", 25))
        self.after_error = float(delays.get("after_error", 300))
        self.minimum = float(delays.get("min", 5))

    def compute(self, action_type="like", actions_done=0, after_error=False):
        lo, hi = self.actions.get(action_type, self.base)
        base_delay = random.uniform(lo, hi) + random.uniform(*self.spread)
        heat = 1.0 + self.heat_multiplier * min(1.0, actions_done / max(1, self.heat_after))
        delay = base_delay * heat
        delay += random.gauss(0, delay * 0.1)
        if after_error:
            delay = max(delay, self.after_error)
        return max(self.minimum, round(delay, 1))

    def pause(self, action_type="like", actions_done=0, after_error=False, logger=None):
        delay = self.compute(action_type, actions_done, after_error)
        if logger:
            logger.info(f"{action_type} sonrasi {delay:.0f} sn bekleniyor (isinma={actions_done})")
        else:
            LOGGER.info(f"{action_type} sonrasi {delay:.0f} sn bekleniyor")
        time.sleep(delay)
        return delay


class LimitEngine:
    """Gunluk butce + saatlik ust sinir kontrolu."""

    def __init__(self, cfg, repo):
        limits = cfg.get("limits", {})
        self.limits = {t: int(limits.get(t, 0)) for t in ACTION_TYPES}
        # unfollows ayrica belirtilmediyse follows butcesini kullan (geriye donuk uyumluluk).
        if not self.limits.get("unfollows"):
            self.limits["unfollows"] = self.limits.get("follows", 0)
        self.hour_fraction = float(limits.get("hourly_cap_fraction", 0.2))
        self.repo = repo

    def daily_cap(self, action_type):
        return self.limits.get(action_type, 0)

    def hourly_cap(self, action_type):
        return max(3, round(self.limits.get(action_type, 0) * self.hour_fraction))

    def check(self, account, action_type, date=None, hour=None):
        date = date or time.strftime("%Y-%m-%d")
        hour = hour if hour is not None else int(time.strftime("%H"))
        used_daily = self.repo.daily_limit(account, action_type, date)
        used_hourly = self.repo.hour_limit(account, action_type, date, hour)
        daily_ok = used_daily < self.daily_cap(action_type)
        hourly_ok = used_hourly < self.hourly_cap(action_type)
        return daily_ok and hourly_ok

    def remaining(self, account, action_type, date=None):
        date = date or time.strftime("%Y-%m-%d")
        used = self.repo.daily_limit(account, action_type, date)
        return max(0, self.daily_cap(action_type) - used)

    def consume(self, account, action_type, date=None, hour=None):
        date = date or time.strftime("%Y-%m-%d")
        hour = hour if hour is not None else int(time.strftime("%H"))
        self.repo.bump_limit(account, action_type, date, hour)


class CooldownRegistry:
    """Hesap bazli yasak/kisit (restriction, sentry vb.) takibi."""

    def __init__(self, repo):
        self.repo = repo

    def set(self, account, key, seconds, reason=""):
        self.repo.set_cooldown(account, key, time.time() + seconds, reason)

    def clear(self, account, key):
        self.repo.clear_cooldown(account, key)

    def active(self, account, key):
        return key in self.repo.active_cooldowns(account)

    def all(self, account):
        return self.repo.active_cooldowns(account)


def active_windows(account_cfg):
    windows = account_cfg.get("windows") or {}
    hours = windows.get("hours") or []
    return [int(h) for h in hours]


def in_window(account_cfg, now=None, tz_name=None):
    hours = active_windows(account_cfg)
    if not hours:
        return True
    if now is not None:
        return now.tm_hour in hours
    windows = account_cfg.get("windows") or {}
    tz_name = windows.get("timezone") or tz_name
    if tz_name:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name)).hour in hours
        except Exception:
            pass
    return time.localtime().tm_hour in hours
