"""告警与通知中心：分级创建、送达模拟、确认、升级。

真实渠道（短信/电话/App push）需接入第三方服务；MVP 阶段：
- 站内告警（数据库）为事实来源；
- 通知动作记录到 notification_log 并打印到控制台，作为渠道接入点。
"""
from __future__ import annotations

from . import database as db

CHANNELS = ["in_app", "sms", "phone", "push"]


def create_alert(user_id: str, *, severity: str, title: str, message: str,
                 type_: str = "health", channels: list[str] | None = None) -> dict:
    alert_id = db.new_id("a_")
    db.execute(
        "INSERT INTO alerts(id,user_id,type,severity,title,message,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (alert_id, user_id, type_, severity, title, message, "pending", db.now()),
    )
    _dispatch(alert_id, user_id, severity, title, message, channels or ["in_app"])
    return get_alert(alert_id)


def _dispatch(alert_id, user_id, severity, title, message, channels):
    """模拟多渠道送达（真实渠道在此接入）。"""
    delivered = []
    for ch in channels:
        delivered.append(ch)
    # 记录通知日志（便于审计与演示）
    db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?)",
        (f"notify_log:{alert_id}", db.dumps({
            "alert_id": alert_id, "user_id": user_id, "severity": severity,
            "channels": delivered, "sent_at": db.now(), "acknowledged": False,
        })),
    )
    print(f"[通知] {severity.upper()} -> user={user_id} channels={delivered} | {title}: {message}")


def get_alert(alert_id: str) -> dict | None:
    a = db.query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    return a


def list_alerts(user_id: str | None = None, limit: int = 50) -> list[dict]:
    if user_id:
        return db.query(
            "SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
    return db.query("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,))


def acknowledge(alert_id: str) -> dict | None:
    db.execute(
        "UPDATE alerts SET status='acknowledged', acknowledged_at=? WHERE id=?",
        (db.now(), alert_id),
    )
    return get_alert(alert_id)


def unread_count(user_id: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM alerts WHERE user_id=? AND status='pending'",
        (user_id,),
    )
    return int(row["c"]) if row else 0
