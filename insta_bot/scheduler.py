import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from insta_bot.poster import Poster
from insta_bot.scraper import Scraper


def compute_next_run(schedule, last_run=None, now=None):
    """Gorev icin sonraki calisma zamanini hesaplar (epoch sn)."""
    now = now if now is not None else time.time()
    every_hours = schedule.get("every_hours")
    if every_hours:
        base = float(last_run) if last_run else now
        return base + float(every_hours) * 3600
    at_times = schedule.get("at") or []
    days = schedule.get("days")
    if not at_times:
        return None
    days = [int(d) for d in days] if days else list(range(7))
    tm = time.localtime(now)
    if tm.tm_wday in days:
        today_candidates = []
        for hhmm in at_times:
            h, m = (int(x) for x in hhmm.split(":"))
            candidate = time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday, h, m, 0,
                                     tm.tm_wday, tm.tm_yday, tm.tm_isdst))
            if candidate > now:
                today_candidates.append(candidate)
        if today_candidates:
            return min(today_candidates)
    for offset in range(1, 8):
        ft = time.localtime(now + offset * 86400)
        if ft.tm_wday not in days:
            continue
        earliest = min(int(hhmm.split(":")[0]) * 60 + int(hhmm.split(":")[1]) for hhmm in at_times)
        h, m = divmod(earliest, 60)
        return time.mktime((ft.tm_year, ft.tm_mon, ft.tm_mday, h, m, 0,
                            ft.tm_wday, ft.tm_yday, ft.tm_isdst))
    return None


def is_due(task, now=None):
    now = now if now is not None else time.time()
    if not task.get("enabled"):
        return False
    return task.get("next_run") is not None and float(task["next_run"]) <= now


class Scheduler:
    """config.yaml'daki gorevleri veritabanina senkronlar ve zamaninda calistirir."""

    def __init__(self, config, repo, runner, logger, provider):
        self.config = config
        self.repo = repo
        self.runner = runner
        self.logger = logger
        self.provider = provider
        self._busy = {}
        self._stop = threading.Event()
        self._thread = None
        self._pool = ThreadPoolExecutor(max_workers=4)
        self._sync_tasks()

    def _sync_tasks(self):
        existing = {(t["name"], t["account"]) for t in self.repo.list_tasks()}
        for spec in self.config.tasks():
            key = (spec.get("name"), spec.get("account"))
            if key in existing:
                continue
            schedule = spec.get("schedule") or {}
            next_run = compute_next_run(schedule)
            task_id = self.repo.add_task(
                spec["name"], spec["account"], spec.get("action", "engage"),
                params=spec.get("params", {}), schedule=schedule,
                enabled=1 if spec.get("enabled", True) else 0)
            self.repo.update_task(task_id, next_run=next_run)
            self.logger.info(f"Gorev eklendi: {spec['name']} ({spec['account']})")

    def start(self):
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self.logger.info("Zamanlayici basladi")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._pool.shutdown(wait=False)
        self.logger.info("Zamanlayici durduruldu")

    def _loop(self):
        while not self._stop.wait(30):
            now = time.time()
            for task in self.repo.list_tasks(enabled_only=True):
                if is_due(task, now):
                    self._dispatch(task)

    def _dispatch(self, task):
        lock = self._busy.setdefault(task["account"], threading.Lock())
        if not lock.acquire(blocking=False):
            self.logger.info(f"Gorev atlandi ({task['account']} mesgul): {task['name']}")
            return
        # Kilit gorev bitene kadar (_run icinde) tutulur; erken submit basarisizsa birak.
        try:
            self._pool.submit(self._run, task, lock)
        except Exception:
            lock.release()
            raise

    def _run(self, task, lock):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.logger.info(f"Gorev basladi: {task['name']} ({task['action']})")
        try:
            self.run_task(task)
            self.repo.update_task(task["id"], last_run=now)
        except Exception as exc:
            self.logger.error(f"Gorev hatasi ({task['name']}): {exc}")
            self.repo.record_action(task["account"], "task", task["name"], "fail", str(exc))
        finally:
            self.repo.update_task(task["id"], next_run=compute_next_run(
                json.loads(task["schedule"] or "{}"), last_run=time.time()))
            lock.release()

    def run_task(self, task):
        params = json.loads(task["params"] or "{}") or {}
        client = self.provider(task["account"])
        action = task["action"]
        if action == "engage":
            self.runner.engage(client, task["account"], **params)
        elif action == "dm":
            self.runner.dm(client, task["account"], **params)
        elif action == "scrape":
            Scraper(self.config, self.repo, self.logger).run(
                client, task["account"], params.get("type"), params.get("target"),
                amount=params.get("amount", 100), out=params.get("out"))
        elif action == "post":
            Poster(self.config, self.repo, self.logger).post(
                client, task["account"], params.get("media", []),
                caption=params.get("caption"), story=params.get("story", False))
        else:
            raise ValueError(f"Bilinmeyen gorev aksiyonu: {action}")
