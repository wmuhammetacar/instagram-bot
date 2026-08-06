import argparse
import json
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler

import uvicorn

from insta_bot import Config, Repo, __version__
from insta_bot.config import ConfigError
from insta_bot.engagement import Runner
from insta_bot.factory import AccountFactory
from insta_bot.metrics import Metrics
from insta_bot.poster import Poster
from insta_bot.scheduler import Scheduler
from insta_bot.scraper import Scraper
from insta_bot.session import AccountError, ChallengePending


def setup_logger(config):
    system = config.get("system", {})
    level = getattr(logging, str(system.get("log_level", "INFO")).upper(), logging.INFO)
    logger = logging.getLogger("insta_bot")
    logger.setLevel(level)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    log_path = config.path(system.get("log_file", "data/logs/bot.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def challenge_prompt(username, choice):
    print(f"\n[CHALLENGE] {username} icin kod gonderildi (kanal: {choice})")
    code = input("Dogrulama kodu: ").strip()
    return code or None


def ask_code():
    return input("2FA dogrulama kodu: ").strip()


def build_parser():
    p = argparse.ArgumentParser(description="Instagram Bot - isletim sistemi")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config-dir", default=None, help="config.yaml/accounts.yaml iceren dizin")
    sub = p.add_subparsers(dest="command", required=True)

    s_login = sub.add_parser("login", help="Hesaba girisi sagla ve oturumu kaydet (all = tum hesaplar)")
    s_login.add_argument("account", nargs="?", default="all",
                         help="Hesap adi (accounts.yaml) veya 'all'")
    s_login.add_argument("--force", action="store_true", help="Kayitli oturumu atla")

    s_status = sub.add_parser("status", help="Hesap ve gunluk istatistik durumu")
    s_engage = sub.add_parser("engage", help="Engajman calistir (takip/begeni/yorum)")
    s_engage.add_argument("account")
    s_engage.add_argument("--hashtags", nargs="*")
    s_engage.add_argument("--competitors", nargs="*")
    s_engage.add_argument("--budget", type=int)
    s_engage.add_argument("--max-follows", type=int)
    s_engage.add_argument("--no-like", action="store_true")
    s_engage.add_argument("--comment", action="store_true")
    s_engage.add_argument("--dry-run", action="store_true")
    s_engage.add_argument("--once", action="store_true", help="Koleksiyon sonrasi bir hedef isle, test icin")

    s_dm = sub.add_parser("dm", help="DM gonder")
    s_dm.add_argument("account")
    s_dm.add_argument("--usernames", nargs="*")
    s_dm.add_argument("--list", help="Kullanici listesi dosyasi")
    s_dm.add_argument("--budget", type=int)
    s_dm.add_argument("--dry-run", action="store_true")

    s_scrape = sub.add_parser("scrape", help="Veri cek (json/csv)")
    s_scrape.add_argument("account")
    s_scrape.add_argument("--type", required=True,
                          choices=["followers", "following", "user", "hashtag", "posts"])
    s_scrape.add_argument("--target", required=True)
    s_scrape.add_argument("--amount", type=int, default=100)
    s_scrape.add_argument("--out")

    s_post = sub.add_parser("post", help="Icerik paylas")
    s_post.add_argument("account")
    s_post.add_argument("--media", nargs="+", required=True)
    s_post.add_argument("--caption")
    s_post.add_argument("--story", action="store_true")
    s_post.add_argument("--dry-run", action="store_true")

    s_targets = sub.add_parser("targets", help="Hedef havuzu yonetimi")
    tsub = s_targets.add_subparsers(dest="action", required=True)
    t_list = tsub.add_parser("list")
    t_list.add_argument("--account")
    t_list.add_argument("--status", default="pending")
    t_list.add_argument("--limit", type=int, default=30)
    t_clear = tsub.add_parser("clear")
    t_clear.add_argument("--account")
    t_clear.add_argument("--status", default="processed")
    t_bl = tsub.add_parser("blacklist")
    t_bl.add_argument("account")
    t_bl.add_argument("--pk", required=True)

    s_tasks = sub.add_parser("tasks", help="Zamanlayici gorevleri")
    tksub = s_tasks.add_subparsers(dest="action", required=True)
    tksub.add_parser("list")
    tk_add = tksub.add_parser("add")
    tk_add.add_argument("--name", required=True)
    tk_add.add_argument("--account", required=True)
    tk_add.add_argument("--action", default="engage")
    tk_add.add_argument("--schedule", default='{"every_hours": 4}')
    tk_del = tksub.add_parser("rm")
    tk_del.add_argument("--id", type=int, required=True)
    tk_tog = tksub.add_parser("toggle")
    tk_tog.add_argument("--id", type=int, required=True)

    s_run = sub.add_parser("run", help="Zamanlayiciyi arka planda calistir (daemon)")
    s_run.add_argument("--once", action="store_true", help="Vadesi gelen gorevleri bir kez calistir")

    s_dash = sub.add_parser("dashboard", help="Web kontrol panelini baslat")
    s_dash.add_argument("--host", default="127.0.0.1")
    s_dash.add_argument("--port", type=int, default=8787)

    s_report = sub.add_parser("report", help="Gunluk rapor uret")
    s_report.add_argument("--date")
    s_report.add_argument("--out")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        config = Config(args.config_dir)
    except ConfigError as exc:
        print(f"\nYAPILANDIRMA HATASI: {exc}\n", file=sys.stderr)
        sys.exit(1)
    repo = Repo(config.path(config.get("system", {}).get("database", "data/bot.db")))
    logger = setup_logger(config)
    factory = AccountFactory(config, repo, logger)

    def connect(name, force=False):
        try:
            return factory.connect(name, force=force,
                                   challenge_callback=challenge_prompt,
                                   verification_callback=ask_code)
        except ChallengePending as exc:
            logger.error(str(exc))
            sys.exit(2)

    cmd = args.command

    if cmd == "login":
        names = [n.get("name") for n in config.accounts()] if args.account in (None, "all") else [args.account]
        for name in names:
            try:
                connect(name, force=args.force)
            except (AccountError, ValueError) as exc:
                logger.error(str(exc))
        return

    if cmd == "status":
        metrics = Metrics(config, repo, logger)
        summary = metrics.daily_summary()
        print(f"\nTarih: {summary['date']}")
        for name, data in summary["accounts"].items():
            state = repo.state(name) or {}
            cooldowns = repo.active_cooldowns(name)
            print(f"\n[{name}] @{config.account(name)['username']}"
                  f"  challenge={'EVET' if state.get('needs_challenge') else 'hayir'}"
                  f"  kisit={len(cooldowns)}")
            print("  takip: %d | begeni: %d | yorum: %d | dm: %d | paylasim: %d | hata: %d" % (
                data["follows"], data["likes"], data["comments"], data["dms"], data["posts"], data["errors"]))
        print("\nHedefler: bekleyen=%d islenen=%d" % (
            repo.targets_count(status="pending"), repo.targets_count(status="processed")))
        return

    if cmd == "engage":
        client = connect(args.account)
        runner = Runner(config, repo, logger, dry_run=args.dry_run)
        if args.once:
            runner.engage(client, args.account, hashtags=args.hashtags,
                          competitors=args.competitors, budget=1,
                          like=not args.no_like, comment=args.comment,
                          max_follows=1)
            return
        runner.engage(client, args.account, hashtags=args.hashtags,
                      competitors=args.competitors, budget=args.budget,
                      like=not args.no_like, comment=args.comment,
                      max_follows=args.max_follows)
        return

    if cmd == "dm":
        client = connect(args.account)
        Runner(config, repo, logger, dry_run=args.dry_run).dm(
            client, args.account, usernames=args.usernames,
            list_file=args.list, budget=args.budget)
        return

    if cmd == "scrape":
        client = connect(args.account)
        Scraper(config, repo, logger).run(client, args.account, args.type,
                                          args.target, amount=args.amount, out=args.out)
        return

    if cmd == "post":
        client = connect(args.account)
        Poster(config, repo, logger, dry_run=args.dry_run).post(
            client, args.account, args.media, caption=args.caption, story=args.story)
        return

    if cmd == "targets":
        if args.action == "list":
            for t in repo.targets(account=args.account, status=args.status, limit=args.limit):
                print(f"{t['score']:>5}  {t['username']:<25} {t['followers']:>7}  "
                      f"{t['source'] or '':<24} {(t['bio'] or '')[:50]}")
        elif args.action == "clear":
            repo.clear_targets(account=args.account, status=args.status)
            print(f"Temizlendi: status={args.status}")
        elif args.action == "blacklist":
            repo.blacklist_add(args.account, args.pk)
            print(f"Kara liste: {args.pk}")
        return

    if cmd == "tasks":
        from insta_bot.scheduler import compute_next_run
        if args.action == "list":
            for t in repo.list_tasks():
                print(f"#{t['id']:<3} {t['name']:<20} {t['account']:<10} {t['action']:<8} "
                      f"next={t['next_run']} {'[aktif]' if t['enabled'] else '[pasif]'}")
        elif args.action == "add":
            schedule = json.loads(args.schedule)
            tid = repo.add_task(args.name, args.account, args.action, params={},
                                schedule=schedule, enabled=1)
            repo.update_task(tid, next_run=compute_next_run(schedule))
            print(f"Gorev eklendi: #{tid}")
        elif args.action == "rm":
            repo.delete_task(args.id)
            print(f"Gorev silindi: #{args.id}")
        elif args.action == "toggle":
            task = next((t for t in repo.list_tasks() if t["id"] == args.id), None)
            if not task:
                sys.exit("Gorev yok")
            repo.update_task(args.id, enabled=0 if task["enabled"] else 1)
            print(f"Gorev #{args.id} -> {'aktif' if not task['enabled'] else 'pasif'}")
        return

    if cmd == "run":
        runner = Runner(config, repo, logger)
        scheduler = Scheduler(config, repo, runner, logger, provider=connect)
        scheduler.start()
        logger.info("Daemon hazir. Cikmak icin Ctrl+C.")
        import threading
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *a: stop.set())
        signal.signal(signal.SIGTERM, lambda *a: stop.set())
        try:
            while not stop.wait(1):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            scheduler.stop()
        return

    if cmd == "dashboard":
        from insta_bot.api import create_app
        app = create_app(config, repo)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return

    if cmd == "report":
        print(Metrics(config, repo, logger).write_report(date=args.date, out=args.out))
        return


if __name__ == "__main__":
    main()
