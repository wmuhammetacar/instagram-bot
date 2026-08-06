import time


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
            types = {"follows": 0, "likes": 0, "comments": 0, "dms": 0, "posts": 0, "errors": 0}
            for row in stats:
                if row["action_type"] in types:
                    if row["status"] == "fail":
                        types["errors"] += row["c"]
                    elif row["status"] == "ok":
                        types[row["action_type"]] += row["c"]
            types["limits"] = {k: self.repo.daily_limit(name, k, date) for k in
                               ("follows", "likes", "comments", "dms", "posts")}
            result[name] = types
        return {"date": date, "accounts": result}

    def hourly_series(self, account, date=None, action_type="follows"):
        date = date or time.strftime("%Y-%m-%d")
        return self.repo.hourly_actions(account, date, action_type)

    def write_report(self, date=None, out=None):
        date = date or time.strftime("%Y-%m-%d")
        summary = self.daily_summary(date)
        lines = [f"# Instagram Bot Gunluk Rapor - {date}", ""]
        for name, data in summary["accounts"].items():
            lines.append(f"## {name}")
            lines.append("")
            for k in ("follows", "likes", "comments", "dms", "posts"):
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
