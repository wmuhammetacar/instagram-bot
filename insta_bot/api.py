import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from insta_bot.engagement import Runner
from insta_bot.factory import AccountFactory
from insta_bot.metrics import Metrics
from insta_bot.session import AccountError, ChallengePending

logger = logging.getLogger("insta_bot.api")


class EngageBody(BaseModel):
    account: str
    hashtags: list = None
    competitors: list = None
    budget: int = None
    like: bool = True
    comment: bool = False
    max_follows: int = None
    dry_run: bool = False


class DmBody(BaseModel):
    account: str
    usernames: list = None
    list_file: str = None
    budget: int = None
    dry_run: bool = False


class TaskBody(BaseModel):
    name: str
    account: str
    action: str = "engage"
    params: dict = None
    schedule: dict = None
    enabled: bool = True


class TargetsBody(BaseModel):
    account: str = None
    status: str = None
    limit: int = 100


class ClearTargetsBody(BaseModel):
    account: str = None
    status: str = "processed"


class BlacklistBody(BaseModel):
    account: str
    pk: str
    username: str = None


class ApiRuntime:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = {}

    def start(self, account, message=""):
        with self._lock:
            self.state[account] = {"status": "running", "message": message,
                                   "started_at": time.strftime("%H:%M:%S")}

    def finish(self, account, message=""):
        with self._lock:
            self.state[account] = {"status": "idle", "message": message,
                                   "started_at": time.strftime("%H:%M:%S")}

    def status(self, account):
        with self._lock:
            return self.state.get(account, {"status": "idle", "message": "", "started_at": ""})


def create_app(config, repo):
    app = FastAPI(title="Instagram Bot Kontrol Paneli", version="1.0")
    runtime = ApiRuntime()
    factory = AccountFactory(config, repo, logger)
    runner = Runner(config, repo, logger)
    metrics = Metrics(config, repo, logger)
    job_locks = {}

    def spawn(account, target):
        lock = job_locks.setdefault(account, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, f"{account} su anda mesgul")
        def work():
            try:
                runtime.start(account, target.__doc__ or "")
                target()
                runtime.finish(account, "basarili")
            except ChallengePending as exc:
                runtime.finish(account, f"challenge: {exc}")
            except AccountError as exc:
                runtime.finish(account, f"hata: {exc}")
            except Exception as exc:
                logger.exception("Islem hatasi")
                runtime.finish(account, f"hata: {exc}")
            finally:
                lock.release()
        threading.Thread(target=work, daemon=True).start()
        return {"queued": True, "account": account}

    def connect_safe(name, force=False):
        try:
            return factory.connect(name, force=force)
        except ChallengePending as exc:
            raise HTTPException(409, str(exc))
        except AccountError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/status")
    def status():
        date = time.strftime("%Y-%m-%d")
        accounts = []
        for acc in config.accounts():
            name = acc["name"]
            state = repo.state(name) or {}
            today = {k: repo.daily_limit(name, k, date) for k in
                     ("follows", "likes", "comments", "dms", "posts")}
            accounts.append({
                "name": name,
                "username": acc["username"],
                "proxy": bool(acc.get("proxy")),
                "windows": (acc.get("windows") or {}).get("hours", []),
                "needs_challenge": bool(state.get("needs_challenge")),
                "last_login": state.get("last_login"),
                "last_error": state.get("last_error"),
                "today": today,
                "limits": config.merged_account(name).get("limits", {}),
                "runtime": runtime.status(name),
                "cooldowns": repo.active_cooldowns(name),
            })
        return {
            "date": date,
            "time": time.strftime("%H:%M:%S"),
            "accounts": accounts,
            "targets": {
                "pending": repo.targets_count(status="pending"),
                "processed": repo.targets_count(status="processed"),
                "blacklisted": repo.targets_count(status="blacklisted"),
                "total": repo.targets_count(),
            },
            "scheduler": {"running": False},
        }

    @app.post("/api/account/{name}/login")
    def account_login(name: str, force: bool = True):
        if not config.account(name):
            raise HTTPException(404, "Hesap yok")

        def work():
            connect_safe(name, force=force)
        spawn(name, work)
        return {"queued": True, "account": name}

    @app.post("/api/engage")
    def api_engage(body: EngageBody):
        def work():
            client = connect_safe(body.account)
            Runner(config, repo, logger, dry_run=body.dry_run).engage(
                client, body.account, hashtags=body.hashtags,
                competitors=body.competitors, budget=body.budget,
                like=body.like, comment=body.comment,
                max_follows=body.max_follows)
        return spawn(body.account, work)

    @app.post("/api/dm")
    def api_dm(body: DmBody):
        def work():
            client = connect_safe(body.account)
            Runner(config, repo, logger, dry_run=body.dry_run).dm(
                client, body.account, usernames=body.usernames,
                list_file=body.list_file, budget=body.budget)
        return spawn(body.account, work)

    @app.get("/api/targets")
    def api_targets(account: str = None, status: str = None, limit: int = 100):
        return repo.targets(account=account, status=status, limit=limit)

    @app.post("/api/targets/clear")
    def api_targets_clear(body: ClearTargetsBody):
        repo.clear_targets(account=body.account, status=body.status)
        return {"cleared": True, "status": body.status}

    @app.post("/api/targets/blacklist")
    def api_targets_blacklist(body: BlacklistBody):
        repo.blacklist_add(body.account, body.pk, body.username)
        return {"blacklisted": True, "pk": body.pk}

    @app.get("/api/actions")
    def api_actions(account: str = None, limit: int = 50):
        return repo.recent_actions(account=account, limit=limit)

    @app.get("/api/hourly")
    def api_hourly(account: str, action_type: str = "follows"):
        return {"hours": metrics.hourly_series(account, action_type=action_type)}

    @app.get("/api/report")
    def api_report(date: str = None):
        return metrics.daily_summary(date)

    @app.get("/api/tasks")
    def api_tasks():
        return repo.list_tasks()

    @app.post("/api/tasks")
    def api_tasks_add(body: TaskBody):
        if not config.account(body.account):
            raise HTTPException(404, "Hesap yok")
        from insta_bot.scheduler import compute_next_run
        task_id = repo.add_task(body.name, body.account, body.action,
                                params=body.params or {}, schedule=body.schedule or {},
                                enabled=1 if body.enabled else 0)
        repo.update_task(task_id, next_run=compute_next_run(body.schedule or {}))
        return {"id": task_id}

    @app.post("/api/tasks/{task_id}/toggle")
    def api_tasks_toggle(task_id: int):
        task = next((t for t in repo.list_tasks() if t["id"] == task_id), None)
        if not task:
            raise HTTPException(404, "Gorev yok")
        repo.update_task(task_id, enabled=0 if task["enabled"] else 1)
        return {"id": task_id, "enabled": not task["enabled"]}

    @app.delete("/api/tasks/{task_id}")
    def api_tasks_delete(task_id: int):
        repo.delete_task(task_id)
        return {"deleted": True}

    web_dir = Path(__file__).resolve().parent / "web"
    app.mount("/assets", StaticFiles(directory=web_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web_dir / "index.html")

    return app
