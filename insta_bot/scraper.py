import csv
import json
from pathlib import Path

from instagrapi.exceptions import ClientError, MediaNotFound, UserNotFound

from insta_bot.utils import json_serial


class Scraper:
    def __init__(self, config, repo, logger):
        self.config = config
        self.repo = repo
        self.logger = logger

    def run(self, client, account_name, kind, target, amount=100, out=None):
        out = out or str(self.config.path(f"data/exports/{account_name}_{kind}_{target}.json"))
        handlers = {
            "followers": lambda: self._followers(client, target, amount),
            "following": lambda: self._following(client, target, amount),
            "user": lambda: self._user(client, target),
            "hashtag": lambda: self._hashtag(client, target, amount),
            "posts": lambda: self._posts(client, target, amount),
        }
        handler = handlers.get(kind)
        if handler is None:
            raise ValueError(f"Bilinmeyen tip: {kind}")
        data = handler()
        self._save(out, data)
        self.repo.record_action(account_name, "scrape", f"{kind}:{target}", "ok",
                                meta={"count": len(data)})
        self.logger.info(f"[{account_name}] {kind} icin {len(data)} kayit yazildi: {out}")
        return data

    def _followers(self, client, target, amount):
        return self._user_list(client, "user_followers", target, amount)

    def _following(self, client, target, amount):
        return self._user_list(client, "user_following", target, amount)

    def _user_list(self, client, fn, target, amount):
        target = target.lstrip("@")
        try:
            uid = client.call("user_id_from_username", target)
            users = client.call(fn, uid, amount=amount)
        except (UserNotFound, ClientError) as exc:
            self.logger.error(f"@{target} cekilemedi: {exc}")
            return []
        return [self._user_brief(u) for u in users.values()]

    def _user(self, client, target):
        target = target.lstrip("@")
        try:
            uid = client.call("user_id_from_username", target)
            info = client.call("user_info", uid)
        except (UserNotFound, ClientError) as exc:
            self.logger.error(f"@{target} cekilemedi: {exc}")
            return {}
        return self._user_brief(info)

    def _hashtag(self, client, target, amount):
        target = target.lstrip("#")
        try:
            medias = client.call("hashtag_medias_recent", target, amount=amount)
        except (MediaNotFound, ClientError) as exc:
            self.logger.error(f"#{target} cekilemedi: {exc}")
            return []
        return [self._media_brief(m) for m in medias]

    def _posts(self, client, target, amount):
        target = target.lstrip("@")
        try:
            uid = client.call("user_id_from_username", target)
            medias = client.call("user_medias", uid, amount=amount)
        except (UserNotFound, ClientError) as exc:
            self.logger.error(f"@{target} cekilemedi: {exc}")
            return []
        return [self._media_brief(m) for m in medias]

    @staticmethod
    def _user_brief(u):
        return {
            "pk": str(u.pk),
            "username": getattr(u, "username", None),
            "full_name": getattr(u, "full_name", None),
            "is_private": 1 if getattr(u, "is_private", False) else 0,
            "is_verified": 1 if getattr(u, "is_verified", False) else 0,
            "followers": getattr(u, "follower_count", 0),
            "following": getattr(u, "following_count", 0),
            "media_count": getattr(u, "media_count", 0),
            "bio": getattr(u, "biography", None),
        }

    @staticmethod
    def _media_brief(m):
        return {
            "pk": str(m.pk),
            "code": getattr(m, "code", None),
            "taken_at": m.taken_at.isoformat(),
            "media_type": m.media_type,
            "like_count": m.like_count,
            "comment_count": m.comment_count,
            "caption": (m.caption_text or "")[:500],
            "user": m.user.username if m.user else None,
            "url": getattr(m, "url", None),
        }

    def _save(self, out, data):
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            if not data:
                path.write_text("", encoding="utf-8")
                return
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(data[0].keys()))
                writer.writeheader()
                writer.writerows(data)
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                       default=json_serial), encoding="utf-8")
