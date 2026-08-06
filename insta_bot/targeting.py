import math
import time
from datetime import date

from instagrapi.exceptions import ClientError, MediaNotFound, UserNotFound


class TargetEngine:
    """Hedef toplama + filtreleme + skorlama."""

    def __init__(self, config, repo, logger):
        self.config = config
        self.repo = repo
        self.logger = logger

    def collect(self, client, account_name, hashtags=None, competitors=None):
        cfg = self.config.merged_account(account_name)
        targeting = cfg.get("targeting", {})
        filters = targeting.get("filters", {})
        sources = targeting.get("sources", {})
        hashtags = hashtags if hashtags is not None else sources.get("hashtags", [])
        competitors = competitors if competitors is not None else sources.get("competitors", [])
        sample = int(targeting.get("competitors_sample", 200))
        my_uid = client.user_id

        rows = []
        seen = set()
        for tag in hashtags:
            tag = str(tag).lstrip("#")
            try:
                medias = client.call("hashtag_medias_recent", tag, amount=20)
            except (ClientError, MediaNotFound) as exc:
                self.logger.warning(f"#{tag} cekilemedi: {exc}")
                continue
            for m in medias:
                if m.user and m.user.pk not in seen:
                    seen.add(m.user.pk)
                    rows.append(self._from_user(m.user, source=f"hashtag:{tag}",
                                                last_media_at=m.taken_at.isoformat()))
        for comp in competitors:
            comp = str(comp).lstrip("@")
            try:
                uid = client.call("user_id_from_username", comp)
                followers = client.call("user_followers", uid, amount=sample)
            except (UserNotFound, ClientError) as exc:
                self.logger.warning(f"Rakip @{comp} cekilemedi: {exc}")
                continue
            for u in followers.values():
                if u.pk not in seen:
                    seen.add(u.pk)
                    rows.append(self._from_user(u, source=f"competitor:{comp}"))

        new_rows, skipped = [], 0
        for row in rows:
            verdict = self.judge(row, filters, my_uid)
            if verdict != "ok":
                self.repo.set_target_status(account_name, row["pk"], verdict)
                skipped += 1
                continue
            row["score"] = self.score(row, targeting.get("scoring", {}), filters)
            row["status"] = "pending"
            new_rows.append(row)
        if not new_rows:
            self.logger.info(f"[{account_name}] Yeni hedef bulunamadi (taranan: {len(rows)}, elenen: {skipped})")
            return {"added": 0, "total": 0}
        result = self.repo.upsert_targets(account_name, new_rows)
        self.logger.info(
            f"[{account_name}] Tarama bitti: {len(rows)} goruldu, {skipped} elendi, "
            f"{result['added']} yeni hedef eklendi (toplam {result['total']})")
        return result

    @staticmethod
    def _from_user(u, source="", last_media_at=None):
        return {
            "pk": str(u.pk),
            "username": getattr(u, "username", None),
            "full_name": getattr(u, "full_name", None),
            "bio": getattr(u, "biography", None),
            "followers": getattr(u, "follower_count", 0) or 0,
            "following": getattr(u, "following_count", 0) or 0,
            "media_count": getattr(u, "media_count", 0) or 0,
            "is_private": 1 if getattr(u, "is_private", False) else 0,
            "is_verified": 1 if getattr(u, "is_verified", False) else 0,
            "source": source,
            "last_media_at": last_media_at,
        }

    @staticmethod
    def judge(row, filters, my_uid):
        if row["pk"] == str(my_uid):
            return "skipped"
        if row["followers"] < int(filters.get("min_followers", 0)):
            return "skipped"
        if row["followers"] > int(filters.get("max_followers", 0)):
            return "skipped"
        if row["following"] > int(filters.get("max_following", 0)):
            return "skipped"
        if row["media_count"] < int(filters.get("min_media_count", 0)):
            return "skipped"
        if row["is_private"] and not filters.get("allow_private", False):
            return "skipped"
        if row["is_verified"] and not filters.get("allow_verified", False):
            return "skipped"
        max_age = int(filters.get("last_media_max_age_days", 0))
        if max_age and row.get("last_media_at"):
            try:
                taken = date.fromisoformat(row["last_media_at"][:10])
                if (date.today() - taken).days > max_age:
                    return "skipped"
            except ValueError:
                pass
        bio = (row.get("bio") or "").lower()
        exclude = [k.lower() for k in filters.get("bio_exclude", [])]
        if any(k in bio for k in exclude):
            return "skipped"
        include = [k.lower() for k in filters.get("bio_include", [])]
        if include and not any(k in bio for k in include):
            return "skipped"
        return "ok"

    @staticmethod
    def score(row, scoring, filters):
        total = 0.0
        bio = (row.get("bio") or "").lower()
        include = [k.lower() for k in filters.get("bio_include", [])]
        keyword_w = float(scoring.get("keyword_hit", 40))
        if include and any(k in bio for k in include):
            total += keyword_w
        elif not include and bio:
            total += keyword_w * 0.5
        balance_w = float(scoring.get("follower_balance", 30))
        f = max(1, row["followers"])
        lo = max(1, int(filters.get("min_followers", 0)))
        hi = max(lo + 1, int(filters.get("max_followers", 0)))
        optimal = math.sqrt(lo * hi)
        deviation = abs(math.log10(f) - math.log10(optimal))
        total += balance_w * max(0.0, 1.0 - deviation / 2.0)
        recency_w = float(scoring.get("recency", 30))
        if row.get("last_media_at"):
            try:
                age = (date.today() - date.fromisoformat(row["last_media_at"][:10])).days
                if age <= 3:
                    total += recency_w
                elif age <= 7:
                    total += recency_w * 0.6
                elif age <= 14:
                    total += recency_w * 0.3
            except ValueError:
                pass
        return round(total, 1)
