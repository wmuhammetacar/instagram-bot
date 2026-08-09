import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
  account TEXT NOT NULL,
  pk TEXT NOT NULL,
  username TEXT,
  full_name TEXT,
  bio TEXT,
  followers INTEGER,
  following INTEGER,
  media_count INTEGER,
  is_private INTEGER DEFAULT 0,
  is_verified INTEGER DEFAULT 0,
  score REAL DEFAULT 0,
  status TEXT DEFAULT 'pending',
  source TEXT,
  last_media_at TEXT,
  first_seen TEXT DEFAULT (datetime('now')),
  last_seen TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (account, pk)
);
CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(account, status, score);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account TEXT NOT NULL,
  action_type TEXT NOT NULL,
  target TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  meta TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_actions_account ON actions(account, created_at);

CREATE TABLE IF NOT EXISTS limits (
  account TEXT NOT NULL,
  date TEXT NOT NULL,
  hour INTEGER NOT NULL,
  action_type TEXT NOT NULL,
  count INTEGER DEFAULT 0,
  PRIMARY KEY (account, date, hour, action_type)
);

CREATE TABLE IF NOT EXISTS processed (
  account TEXT NOT NULL,
  action_type TEXT NOT NULL,
  target TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (account, action_type, target)
);

CREATE TABLE IF NOT EXISTS cooldowns (
  account TEXT NOT NULL,
  key TEXT NOT NULL,
  until REAL,
  reason TEXT,
  PRIMARY KEY (account, key)
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  account TEXT NOT NULL,
  action TEXT NOT NULL,
  params TEXT,
  schedule TEXT,
  enabled INTEGER DEFAULT 1,
  last_run TEXT,
  next_run TEXT
);

CREATE TABLE IF NOT EXISTS account_state (
  account TEXT PRIMARY KEY,
  needs_challenge INTEGER DEFAULT 0,
  last_login TEXT,
  last_error TEXT
);
"""


class Repo:
    def __init__(self, path="data/bot.db"):
        self.path = str(path)
        self._lock = threading.RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql, params=()):
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def close(self):
        with self._lock:
            self._conn.close()

    # ---------------- targets ----------------

    def upsert_targets(self, account, rows):
        added = 0
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            row = self._one(
                "SELECT status FROM targets WHERE account=? AND pk=?", (account, r["pk"]))
            self._exec(
                """INSERT INTO targets (account, pk, username, full_name, bio, followers, following,
                   media_count, is_private, is_verified, score, status, source, last_media_at, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(account, pk) DO UPDATE SET
                   username=excluded.username, full_name=excluded.full_name, bio=excluded.bio,
                   followers=excluded.followers, following=excluded.following,
                   media_count=excluded.media_count, is_private=excluded.is_private,
                   is_verified=excluded.is_verified, score=excluded.score, source=excluded.source,
                   last_media_at=excluded.last_media_at, last_seen=excluded.last_seen""",
                (account, r["pk"], r.get("username"), r.get("full_name"), r.get("bio"),
                 r.get("followers"), r.get("following"), r.get("media_count"),
                 int(r.get("is_private", 0)), int(r.get("is_verified", 0)),
                 r.get("score", 0.0), r.get("status", "pending"), r.get("source"),
                 r.get("last_media_at"), now))
            if row is None:
                added += 1
        total = self._one("SELECT COUNT(*) AS c FROM targets WHERE account=?", (account,))["c"]
        return {"added": added, "total": total}

    def pending_targets(self, account, limit=20, min_score=0.0):
        return self._query(
            """SELECT * FROM targets WHERE account=? AND status='pending' AND score>=?
               ORDER BY score DESC LIMIT ?""", (account, min_score, limit))

    def set_target_status(self, account, pk, status):
        self._exec("UPDATE targets SET status=? WHERE account=? AND pk=?", (status, account, pk))

    def clear_targets(self, account=None, status="processed"):
        params = (status,)
        sql = "DELETE FROM targets WHERE status=?"
        if account:
            sql += " AND account=?"
            params = (status, account)
        self._exec(sql, params)

    def targets_count(self, account=None, status=None):
        sql = "SELECT COUNT(*) AS c FROM targets"
        cond, params = [], []
        if account:
            cond.append("account=?")
            params.append(account)
        if status:
            cond.append("status=?")
            params.append(status)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        return self._one(sql, params)["c"]

    def targets(self, account=None, status=None, limit=100):
        sql = "SELECT * FROM targets"
        cond, params = [], []
        if account:
            cond.append("account=?")
            params.append(account)
        if status:
            cond.append("status=?")
            params.append(status)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY score DESC LIMIT ?"
        params.append(limit)
        return self._query(sql, params)

    def blacklist_add(self, account, pk, username=None):
        self._exec(
            """INSERT INTO targets (account, pk, username, status, first_seen)
               VALUES (?,?,?,'blacklisted',datetime('now'))
               ON CONFLICT(account, pk) DO UPDATE SET status='blacklisted'""",
            (account, str(pk), username))

    # ---------------- processed ----------------

    def processed_set(self, account, action_type):
        rows = self._query(
            "SELECT target FROM processed WHERE account=? AND action_type=?", (account, action_type))
        return {r["target"] for r in rows}

    def is_processed(self, account, action_type, target):
        row = self._one(
            "SELECT 1 AS x FROM processed WHERE account=? AND action_type=? AND target=?",
            (account, action_type, str(target)))
        return row is not None

    def mark_processed(self, account, action_type, target):
        self._exec(
            """INSERT OR IGNORE INTO processed (account, action_type, target)
               VALUES (?,?,?)""", (account, action_type, str(target)))

    # ---------------- actions ----------------

    def record_action(self, account, action_type, target=None, status="ok", error=None, meta=None):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self._exec(
            """INSERT INTO actions (account, action_type, target, status, error, meta, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (account, action_type, target, status, error,
             json.dumps(meta, ensure_ascii=False) if meta else None, now))

    def recent_actions(self, account=None, limit=50):
        sql = "SELECT * FROM actions"
        params = []
        if account:
            sql += " WHERE account=?"
            params.append(account)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self._query(sql, params)

    def first_action_date(self, account):
        # Hesabin ilk aksiyon tarihi (YYYY-MM-DD). Isinma rampasi icin "hesap yasi"
        # buradan hesaplanir. Hic aksiyon yoksa None doner (gun 0 kabul edilir).
        row = self._one(
            "SELECT MIN(created_at) AS t FROM actions WHERE account=?", (account,))
        if not row or not row["t"]:
            return None
        return str(row["t"])[:10]

    def unfollow_candidates(self, account, before_ts, limit=200):
        # Gercekten takip edilmis (follow/ok) ve henuz basariyla unfollow edilmemis,
        # `before_ts`ten once takip edilen kullanicilar (en eskiden yeniye).
        rows = self._query(
            """SELECT target, MIN(created_at) AS followed_at FROM actions a
               WHERE account=? AND action_type='follow' AND status='ok'
                 AND target IS NOT NULL AND created_at <= ?
                 AND NOT EXISTS (
                     SELECT 1 FROM actions u
                     WHERE u.account=a.account AND u.action_type='unfollow'
                       AND u.status='ok' AND u.target=a.target)
               GROUP BY target
               ORDER BY followed_at ASC
               LIMIT ?""", (account, before_ts, limit))
        return [r["target"] for r in rows]

    def action_stats(self, account, since=None):
        sql = """SELECT action_type, status, COUNT(*) AS c FROM actions WHERE account=?"""
        params = [account]
        if since:
            sql += " AND created_at>=?"
            params.append(since)
        sql += " GROUP BY action_type, status"
        return self._query(sql, params)

    def hourly_actions(self, account, date, action_type):
        # actions tablosunda ayri 'hour' sutunu yok; saati created_at'ten turetiyoruz
        # (format: "YYYY-MM-DD HH:MM:SS" -> 12. karakterden itibaren 2 hane).
        rows = self._query(
            """SELECT CAST(substr(created_at, 12, 2) AS INTEGER) AS hour, COUNT(*) AS c
               FROM actions
               WHERE account=? AND action_type=? AND status='ok' AND created_at LIKE ?
               GROUP BY hour""", (account, action_type, f"{date}%"))
        counts = [0] * 24
        for r in rows:
            h = r["hour"]
            if h is not None and 0 <= h < 24:
                counts[h] = r["c"]
        return counts

    # ---------------- limits ----------------

    def bump_limit(self, account, action_type, date, hour):
        self._exec(
            """INSERT INTO limits (account, date, hour, action_type, count) VALUES (?,?,?,?,1)
               ON CONFLICT(account, date, hour, action_type)
               DO UPDATE SET count = count + 1""",
            (account, date, hour, action_type))

    def daily_limit(self, account, action_type, date=None):
        date = date or time.strftime("%Y-%m-%d")
        row = self._one(
            "SELECT COALESCE(SUM(count),0) AS c FROM limits WHERE account=? AND action_type=? AND date=?",
            (account, action_type, date))
        return int(row["c"])

    def hour_limit(self, account, action_type, date, hour):
        row = self._one(
            "SELECT count FROM limits WHERE account=? AND action_type=? AND date=? AND hour=?",
            (account, action_type, date, hour))
        return int(row["count"]) if row else 0

    def today_limits(self, account, date):
        rows = self._query(
            "SELECT action_type, SUM(count) AS c FROM limits WHERE account=? AND date=? GROUP BY action_type",
            (account, date))
        return {r["action_type"]: int(r["c"]) for r in rows}

    # ---------------- cooldowns ----------------

    def set_cooldown(self, account, key, until_ts, reason=""):
        self._exec(
            """INSERT INTO cooldowns (account, key, until, reason) VALUES (?,?,?,?)
               ON CONFLICT(account, key) DO UPDATE SET until=excluded.until, reason=excluded.reason""",
            (account, key, float(until_ts), reason))

    def active_cooldowns(self, account):
        now = time.time()
        rows = self._query(
            "SELECT key, until, reason FROM cooldowns WHERE account=? AND until>?",
            (account, now))
        return {r["key"]: {"until": r["until"], "reason": r["reason"]} for r in rows}

    def clear_cooldown(self, account, key):
        self._exec("DELETE FROM cooldowns WHERE account=? AND key=?", (account, key))

    # ---------------- account state ----------------

    def set_state(self, account, **fields):
        row = self._one("SELECT 1 AS x FROM account_state WHERE account=?", (account,))
        if row:
            sets = ", ".join(f"{k}=?" for k in fields)
            self._exec(f"UPDATE account_state SET {sets} WHERE account=?", (*fields.values(), account))
        else:
            cols = ", ".join(fields.keys())
            marks = ", ".join("?" for _ in fields)
            self._exec(
                f"INSERT INTO account_state (account, {cols}) VALUES (?,{marks})",
                (account, *fields.values()))

    def state(self, account):
        return self._one("SELECT * FROM account_state WHERE account=?", (account,))

    # ---------------- tasks ----------------

    def add_task(self, name, account, action, params=None, schedule=None, enabled=1):
        self._exec(
            """INSERT INTO tasks (name, account, action, params, schedule, enabled)
               VALUES (?,?,?,?,?,?)""",
            (name, account, action, json.dumps(params, ensure_ascii=False),
             json.dumps(schedule, ensure_ascii=False), int(enabled)))
        return self._one("SELECT MAX(id) AS id FROM tasks")["id"]

    def update_task(self, task_id, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE tasks SET {sets} WHERE id=?", (*fields.values(), task_id))

    def list_tasks(self, enabled_only=False):
        sql = "SELECT * FROM tasks"
        params = []
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        return self._query(sql, params)

    def delete_task(self, task_id):
        self._exec("DELETE FROM tasks WHERE id=?", (task_id,))
