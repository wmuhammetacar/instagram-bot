import random
import time
from pathlib import Path

from instagrapi.exceptions import ClientError

from insta_bot.security import LimitEngine


class Poster:
    def __init__(self, config, repo, logger, dry_run=False):
        self.config = config
        self.repo = repo
        self.logger = logger
        self.dry_run = dry_run

    def post(self, client, account_name, paths, caption=None, story=False):
        cfg = self.config.merged_account(account_name)
        limits = LimitEngine(cfg, self.repo)
        posting = cfg.get("posting", {})
        if not limits.check(account_name, "posts"):
            self.logger.warning(f"[{account_name}] Gunluk paylasim limiti doldu")
            return {"posts": 0}
        caption = caption or (random.choice(posting.get("rotation") or [""]) if posting.get("rotation") else "")
        caption = self._render(caption, client, posting)
        media = [Path(p) for p in paths]
        for p in media:
            if not p.exists():
                raise FileNotFoundError(f"Dosya yok: {p}")
        if self.dry_run:
            self.logger.info(f"[KURU CALISMA] [{account_name}] Paylasim: {[str(p) for p in media]} story={story}")
            return {"posts": 1}
        try:
            if story:
                self._story(client, media)
            else:
                self._feed(client, media, caption)
            self.repo.record_action(account_name, "post", ";".join(str(p) for p in media), "ok",
                                    meta={"story": story, "caption": caption[:200]})
            limits.consume(account_name, "posts")
            return {"posts": 1}
        except ClientError as exc:
            self.logger.error(f"[{account_name}] Paylasim basarisiz: {exc}")
            self.repo.record_action(account_name, "post", ";".join(str(p) for p in media), "fail", str(exc))
            return {"posts": 0}

    def _feed(self, client, media, caption):
        if len(media) == 1:
            p = media[0]
            if p.suffix.lower() in (".mp4", ".mov", ".m4v"):
                m = client.call("video_upload", str(p), caption)
            else:
                m = client.call("photo_upload", str(p), caption)
            self.logger.info(f"Paylasildi: https://instagram.com/p/{m.code}")
        else:
            m = client.call("album_upload", [str(p) for p in media], caption)
            self.logger.info(f"Carousel paylasildi: https://instagram.com/p/{m.code}")

    def _story(self, client, media):
        for p in media:
            if p.suffix.lower() in (".mp4", ".mov", ".m4v"):
                m = client.call("video_upload_to_story", str(p))
            else:
                m = client.call("photo_upload_to_story", str(p))
            self.logger.info(f"Story paylasildi: {m.pk}")

    def _render(self, caption, client, posting):
        if caption:
            caption = (caption
                       .replace("{username}", client.username)
                       .replace("{date}", time.strftime("%d.%m.%Y"))
                       .replace("{time}", time.strftime("%H:%M")))
        if "{hashtags}" in caption or not caption:
            bank = posting.get("hashtag_bank", {})
            count = int(posting.get("hashtags_per_post", 8))
            tags = []
            for group in ("big", "medium", "small"):
                pool = bank.get(group) or []
                take = max(1, count // 3) if pool else 0
                tags.extend(random.sample(pool, min(take, len(pool))))
            tags = tags[:count]
            caption = (caption or "").replace("{hashtags}", " ".join(tags))
            if not caption.strip() and tags:
                caption = " ".join(tags)
        return caption
