import time

# actions tablosu tekil aksiyon adi yazar (follow/unfollow/like/comment/dm/post);
# rapor, limitler ve panel cogul anahtar kullanir. Iki yon arasinda esleme:
ACTION_TO_PLURAL = {"follow": "follows", "unfollow": "unfollows", "like": "likes",
                    "comment": "comments", "dm": "dms", "post": "posts"}
PLURAL_TO_ACTION = {v: k for k, v in ACTION_TO_PLURAL.items()}


class Metrics:
    def __init__(self, config, repo, logger):
        self.config = config
        self.repo = repo
        self.logger = logger

    def daily_summary(self, date=None):
        date = date or time.strftime("%Y-%m-%d")
        result = {}
        for acc in self.config.accounts():
            name = acc["name"]
            since = f"{date} 00:00:00"
            stats = self.repo.action_stats(name, since=since)
            types = {"follows": 0, "unfollows": 0, "likes": 0, "comments": 0,
                     "dms": 0, "posts": 0, "errors": 0}
            for row in stats:
                key = ACTION_TO_PLURAL.get(row["action_type"], row["action_type"])
                if key in types:
                    if row["status"] == "fail":
                        types["errors"] += row["c"]
                    elif row["status"] == "ok":
                        types[key] += row["c"]
            types["limits"] = {k: self.repo.daily_limit(name, k, date) for k in
                               ("follows", "unfollows", "likes", "comments", "dms", "posts")}
            result[name] = types
        return {"date": date, "accounts": result}

    def analytics(self, account, since=None):
        """Kaynak bazli takip -> geri-takip donusumu. Geri-takip, unfollow akisinda
        (keep_followers) tespit edilip 'followback' aksiyonu olarak kaydedilir."""
        import json as _json
        follows = self.repo.actions_by_type(account, "follow", since)
        followbacks = self.repo.actions_by_type(account, "followback", since)
        fb_targets = {r["target"] for r in followbacks}

        sources = {}
        for row in follows:
            src = "bilinmiyor"
            if row.get("meta"):
                try:
                    src = (_json.loads(row["meta"]) or {}).get("source") or "bilinmiyor"
                except (ValueError, TypeError):
                    pass
            bucket = sources.setdefault(src, {"follows": 0, "followbacks": 0})
            bucket["follows"] += 1
            if row["target"] in fb_targets:
                bucket["followbacks"] += 1
        for bucket in sources.values():
            bucket["rate"] = (round(bucket["followbacks"] / bucket["follows"], 3)
                              if bucket["follows"] else 0.0)

        total_f = sum(b["follows"] for b in sources.values())
        total_fb = sum(b["followbacks"] for b in sources.values())
        return {
            "account": account,
            "sources": dict(sorted(sources.items(), key=lambda kv: kv[1]["follows"], reverse=True)),
            "totals": {
                "follows": total_f,
                "followbacks": total_fb,
                "rate": round(total_fb / total_f, 3) if total_f else 0.0,
            },
        }

    def hourly_series(self, account, date=None, action_type="follows"):
        date = date or time.strftime("%Y-%m-%d")
        # Cagiran cogul ('follows') veya tekil ('follow') gonderebilir; actions
        # tablosu tekil sakladigindan tekile normalize et.
        singular = PLURAL_TO_ACTION.get(action_type, action_type)
        return self.repo.hourly_actions(account, date, singular)

    def write_report(self, date=None, out=None):
        date = date or time.strftime("%Y-%m-%d")
        summary = self.daily_summary(date)
        lines = [f"# Instagram Bot Gunluk Rapor - {date}", ""]
        for name, data in summary["accounts"].items():
            lines.append(f"## {name}")
            lines.append("")
            for k in ("follows", "unfollows", "likes", "comments", "dms", "posts"):
                lines.append(f"- {k}: {data[k]}")
            lines.append(f"- hata: {data['errors']}")
            limits = data["limits"]
            used = {k: data[k] for k in limits}
            lines.append("")
            lines.append("| aksiyon | kullanim | limit | oran |")
            lines.append("|---|---|---|---|")
            for k, cap in limits.items():
                ratio = f"%{int(used[k] / cap * 100)}" if cap else "-"
                lines.append(f"| {k} | {used[k]} | {cap} | {ratio} |")
            lines.append("")
        report = "\n".join(lines)
        if out:
            path = self.config.path(out if isinstance(out, str) else f"data/reports/{date}.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        return report
