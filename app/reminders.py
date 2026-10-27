"""医嘱/测量提醒：创建、今日待办、执行记录，以及后台调度线程。

调度简化模型：cron 支持 'daily HH:MM' 或 'HH:MM'（每日一次）。
到点后生成提醒告警；执行（服药/测量）通过 adherence_logs 记录。
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, date

from . import alerts
from . import config
from . import database as db

_stop = threading.Event()
_thread: threading.Thread | None = None


def _parse_daily(cron: str) -> tuple[int, int] | None:
    m = re.match(r"(?:daily\s+)?(\d{1,2}):(\d{2})", (cron or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def create_reminder(user_id: str, *, kind: str, title: str, detail: str = "",
                    cron: str = "08:00", enabled: bool = True) -> dict:
    rid = db.new_id("rem_")
    db.execute(
        "INSERT INTO reminders(id,user_id,kind,title,detail,cron,enabled,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (rid, user_id, kind, title, detail, cron, 1 if enabled else 0, db.now()),
    )
    return db.query_one("SELECT * FROM reminders WHERE id=?", (rid,))


def list_reminders(user_id: str) -> list[dict]:
    return db.query("SELECT * FROM reminders WHERE user_id=? ORDER BY cron", (user_id,))


def record_adherence(reminder_id: str, user_id: str, taken: bool = True, note: str = "") -> dict:
    db.execute(
        "INSERT INTO adherence_logs(reminder_id,user_id,taken,taken_at,note) VALUES(?,?,?,?,?)",
        (reminder_id, user_id, 1 if taken else 0, db.now(), note),
    )
    return {"reminder_id": reminder_id, "taken": taken, "taken_at": db.now()}


def _taken_today(reminder_id: str) -> bool:
    today = date.today().isoformat()
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM adherence_logs WHERE reminder_id=? AND taken=1 "
        "AND substr(taken_at,1,10)=?",
        (reminder_id, today),
    )
    return bool(row and row["c"])


def due_reminders(user_id: str) -> list[dict]:
    """今日到点且尚未执行的提醒（供前端展示待办）。"""
    now = datetime.now()
    due = []
    for r in list_reminders(user_id):
        if not r.get("enabled"):
            continue
        t = _parse_daily(r["cron"])
        if not t:
            continue
        scheduled = now.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
        if scheduled <= now and not _taken_today(r["id"]):
            due.append({**r, "taken_today": False})
    return due


def check_due() -> int:
    """后台轮询：到点未提醒的，生成提醒告警（每天一次）。"""
    now = datetime.now()
    fired = 0
    for r in db.query("SELECT * FROM reminders WHERE enabled=1"):
        t = _parse_daily(r["cron"])
        if not t:
            continue
        scheduled = now.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
        if scheduled <= now:
            key = f"remind_fired:{r['id']}"
            last = db.query_one("SELECT value FROM settings WHERE key=?", (key,))
            if last and last["value"] == date.today().isoformat():
                continue
            if not _taken_today(r["id"]):
                alerts.create_alert(
                    r["user_id"], severity="info", type_="reminder",
                    title=f"提醒：{r['title']}",
                    message=r.get("detail") or r["title"],
                    channels=["in_app"],
                )
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                       (key, date.today().isoformat()))
            fired += 1
    return fired


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def _loop():
        while not _stop.is_set():
            try:
                check_due()
            except Exception as e:  # noqa: BLE001
                print(f"[reminder] error: {e}")
            _stop.wait(config.REMINDER_POLL_SECONDS)

    _thread = threading.Thread(target=_loop, daemon=True, name="reminder-scheduler")
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
