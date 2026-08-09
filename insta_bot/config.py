import os
from copy import deepcopy
from pathlib import Path

import yaml


def _deep_merge(base, override):
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigError(Exception):
    """Yapilandirma dosyalarinda tespit edilen hata."""


def _check_range(section, key, value, low, high):
    if not isinstance(value, (int, float)) or value < low or value > high:
        raise ConfigError(
            f"config.yaml: [{section}] {key} = {value} degeri gecersiz "
            f"({low}-{high} araliginda sayi olmali)")


def _check_delay_range(section, name, lo, hi):
    if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 0 <= lo <= hi):
        raise ConfigError(f"config.yaml: [{section}] {name} gecersiz aralik [{lo}, {hi}]")


class Config:
    def __init__(self, base_dir=None):
        self.base = Path(base_dir or Path(__file__).resolve().parent.parent)
        self.global_path = self.base / "config.yaml"
        self.accounts_path = self.base / "accounts.yaml"
        self._global = {}
        self._accounts = []
        self._load_env()
        self.reload()
        self.validate()

    def validate(self):
        if not self.global_path.exists():
            raise ConfigError(f"{self.global_path} bulunamadi. Ornek: cp config.yaml.example config.yaml")
        if not self.accounts_path.exists():
            raise ConfigError(f"{self.accounts_path} bulunamadi. Ornek: cp accounts.yaml.example accounts.yaml")

        limits = self._global.get("limits", {})
        for key in ("follows", "likes", "comments", "dms", "posts"):
            if key not in limits:
                raise ConfigError(f"config.yaml: [limits] {key} tanimli degil")
            _check_range("limits", key, limits[key], 0, 100000)
        _check_range("limits", "hourly_cap_fraction", limits.get("hourly_cap_fraction", 1.0), 0.01, 1.0)

        delays = self._global.get("delays", {})
        base = delays.get("base", [45, 120])
        spread = delays.get("spread", [10, 60])
        _check_delay_range("delays", "base", base[0], base[1])
        _check_delay_range("delays", "spread", spread[0], spread[1])
        for name, rng in (delays.get("actions") or {}).items():
            _check_delay_range("delays.actions", name, rng[0], rng[1])
        _check_range("delays", "min", delays.get("min", 5), 0, 3600)
        _check_range("delays", "after_error", delays.get("after_error", 300), 0, 86400)
        _check_range("delays", "heat_multiplier", delays.get("heat_multiplier", 2.0), 0, 100)

        targeting = self._global.get("targeting", {})
        filters = targeting.get("filters", {})
        _check_range("targeting.filters", "min_followers", filters.get("min_followers", 0), 0, 10**9)
        _check_range("targeting.filters", "max_followers", filters.get("max_followers", 0), 0, 10**9)
        if filters.get("min_followers", 0) > filters.get("max_followers", 0):
            raise ConfigError("config.yaml: min_followers, max_followers'tan buyuk olamaz")
        _check_range("targeting.filters", "max_following", filters.get("max_following", 0), 0, 10**9)
        _check_range("targeting.filters", "min_media_count", filters.get("min_media_count", 0), 0, 10**6)
        _check_range("targeting", "default_budget_per_run",
                     targeting.get("default_budget_per_run", 20), 1, 10000)

        comments = self._global.get("comments", {})
        dm = self._global.get("dm", {})
        if not comments.get("rotation"):
            raise ConfigError("config.yaml: [comments] rotation bos olmamali (en az 1 mesaj)")
        if not dm.get("rotation"):
            raise ConfigError("config.yaml: [dm] rotation bos olmamali (en az 1 mesaj)")

        seen_names = set()
        for acc in self._accounts:
            name = acc.get("name")
            if not name:
                raise ConfigError("accounts.yaml: isimsiz hesap bulundu (name zorunlu)")
            if name in seen_names:
                raise ConfigError(f"accounts.yaml: '{name}' hesap adi birden fazla kez geciliyor")
            seen_names.add(name)
            if not acc.get("username"):
                raise ConfigError(f"accounts.yaml: '{name}' icin username bos")
            if acc.get("enabled", True) and not self._resolve_password(acc):
                raise ConfigError(
                    f"accounts.yaml: '{name}' icin sifre yok. .env dosyasinda "
                    f"IG_PW_{name.upper()} veya IG_PASSWORD tanimlayin")
        if not any(a.get("enabled", True) for a in self._accounts):
            raise ConfigError("accounts.yaml: aktif (enabled=true) hicbir hesap yok")

        return True

    def reload(self):
        self._global = {}
        if self.global_path.exists():
            self._global = yaml.safe_load(self.global_path.read_text(encoding="utf-8")) or {}
        self._accounts = []
        if self.accounts_path.exists():
            data = yaml.safe_load(self.accounts_path.read_text(encoding="utf-8")) or {}
            self._accounts = data.get("accounts", []) or []

    def _load_env(self):
        env_path = self.base / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Cevreleyen tirnaklari kaldir: IG_PASSWORD="gizli sifre" -> gizli sifre
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ.setdefault(key, value)

    def get(self, key, default=None):
        return self._global.get(key, default)

    def path(self, rel):
        return self.base / rel

    def accounts(self, enabled_only=True):
        result = []
        for acc in self._accounts:
            acc = dict(acc)
            if enabled_only and not acc.get("enabled", True):
                continue
            acc["password"] = self._resolve_password(acc)
            result.append(acc)
        return result

    def account(self, name):
        for acc in self._accounts:
            if acc.get("name") == name:
                acc = dict(acc)
                acc["password"] = self._resolve_password(acc)
                return acc
        return None

    def _resolve_password(self, acc):
        pw = acc.get("password")
        if pw:
            return pw
        env_key = acc.get("password_env") or f"IG_PW_{acc.get('name', '').upper()}"
        if env_key in os.environ:
            return os.environ[env_key]
        return os.environ.get("IG_PASSWORD", "")

    def merged_account(self, name):
        base = {
            "limits": deepcopy(self.get("limits", {})),
            "delays": deepcopy(self.get("delays", {})),
            "targeting": deepcopy(self.get("targeting", {})),
            "comments": deepcopy(self.get("comments", {})),
            "dm": deepcopy(self.get("dm", {})),
            "posting": deepcopy(self.get("posting", {})),
            "unfollow": deepcopy(self.get("unfollow", {})),
            "warmup": deepcopy(self.get("warmup", {})),
            "humanize": deepcopy(self.get("humanize", {})),
            "windows": {},
        }
        acc = self.account(name) or {}
        base.update({k: v for k, v in acc.items() if k not in ("name", "username", "password", "proxy", "enabled")})
        return base

    def tasks(self):
        return self.get("tasks", []) or []
