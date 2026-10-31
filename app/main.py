"""MedAgent 后端入口：Starlette 应用 + 路由 + 静态资源。

直接运行 `python -m app.main` 会启动 uvicorn 并自动打开浏览器（桌面式体验）。
"""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime, timedelta

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from . import alerts
from . import config
from . import database as db
from . import reminders
from . import reports
from . import seed as seed_mod
from . import triage


# ---------- 工具 ----------
def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


async def _body(request: Request) -> dict:
    try:
        raw = await request.body()
        return json.loads(raw) if raw else {}
    except (ValueError, json.JSONDecodeError):
        return {}


def _latest_metrics(user_id: str) -> dict[str, float]:
    rows = db.query(
        "SELECT type, value FROM metrics WHERE user_id=? AND id IN "
        "(SELECT MAX(id) FROM metrics WHERE user_id=? GROUP BY type)",
        (user_id, user_id),
    )
    return {r["type"]: r["value"] for r in rows}


def _series(user_id: str, mtype: str, days: int) -> list[dict]:
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.query(
        "SELECT value, measured_at FROM metrics WHERE user_id=? AND type=? AND measured_at>=? ORDER BY measured_at",
        (user_id, mtype, since),
    )
    return [{"value": r["value"], "at": r["measured_at"]} for r in rows]


def _metric_rows(user_id: str, mtype: str | None, limit: int = 500) -> list[dict]:
    if mtype:
        return db.query(
            "SELECT * FROM metrics WHERE user_id=? AND type=? ORDER BY measured_at DESC LIMIT ?",
            (user_id, mtype, limit),
        )
    return db.query(
        "SELECT * FROM metrics WHERE user_id=? ORDER BY measured_at DESC LIMIT ?",
        (user_id, limit),
    )


# ---------- 业务路由 ----------
async def health(_: Request) -> Response:
    return _json({"status": "ok", "service": "MedAgent", "time": db.now()})


async def do_seed(request: Request) -> Response:
    body = await _body(request)
    result = seed_mod.seed_demo(force=bool(body.get("force", False)))
    return _json({"ok": True, **result})


async def create_user(request: Request) -> Response:
    body = await _body(request)
    uid = db.new_id("u_")
    name = body.get("name") or "未命名使用者"
    db.execute(
        "INSERT INTO users(id,name,gender,birth_date,height_cm,weight_kg,blood_type,"
        "medical_history,allergies,current_medications,phone,address,emergency_contacts,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, name, body.get("gender"), body.get("birth_date"), body.get("height_cm"),
         body.get("weight_kg"), body.get("blood_type"),
         db.dumps(body.get("medical_history", [])), db.dumps(body.get("allergies", [])),
         db.dumps(body.get("current_medications", [])), body.get("phone"), body.get("address"),
         db.dumps(body.get("emergency_contacts", [])), db.now()),
    )
    for g in body.get("guardians", []):
        db.execute(
            "INSERT INTO guardians(id,user_id,name,phone,relation,is_primary,notify_channels,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (db.new_id("g_"), uid, g.get("name"), g.get("phone"), g.get("relation"),
             1 if g.get("is_primary") else 0, db.dumps(g.get("notify_channels", ["in_app"])), db.now()),
        )
    return _json({"ok": True, "user_id": uid}, 201)


async def list_users(_: Request) -> Response:
    rows = db.query("SELECT id,name,gender,birth_date,phone,medical_history,allergies,current_medications FROM users")
    for r in rows:
        r["medical_history"] = db.loads(r.get("medical_history"), [])
        r["allergies"] = db.loads(r.get("allergies"), [])
        r["current_medications"] = db.loads(r.get("current_medications"), [])
    return _json({"users": rows})


async def get_user(request: Request) -> Response:
    uid = request.path_params["id"]
    row = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not row:
        return _json({"error": "用户不存在"}, 404)
    for f in ("medical_history", "allergies", "current_medications", "emergency_contacts"):
        row[f] = db.loads(row.get(f), [])
    row["guardians"] = db.query("SELECT * FROM guardians WHERE user_id=?", (uid,))
    return _json({"user": row})


async def update_user(request: Request) -> Response:
    uid = request.path_params["id"]
    body = await _body(request)
    fields = ["name", "gender", "birth_date", "height_cm", "weight_kg", "blood_type",
              "phone", "address"]
    sets, params = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            params.append(body[f])
    for f in ("medical_history", "allergies", "current_medications", "emergency_contacts"):
        if f in body:
            sets.append(f"{f}=?")
            params.append(db.dumps(body[f]))
    if not sets:
        return _json({"ok": False, "error": "无可更新字段"}, 400)
    params.append(uid)
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(params))
    return _json({"ok": True})


async def add_metrics(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    items = body.get("metrics")
    if items is None:
        items = [body]
    if not isinstance(items, list):
        return _json({"error": "metrics 应为数组"}, 400)
    inserted = 0
    for m in items:
        mtype = m.get("type")
        value = m.get("value")
        if mtype is None or value is None:
            continue
        ref = config.METRIC_REFERENCE.get(mtype, {})
        db.execute(
            "INSERT INTO metrics(user_id,device_id,type,value,unit,measured_at,source,quality) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (user_id, m.get("device_id"), mtype, float(value),
             m.get("unit") or ref.get("unit", ""),
             m.get("measured_at") or db.now(), m.get("source", "manual"),
             m.get("quality", "valid")),
        )
        inserted += 1
    return _json({"ok": True, "inserted": inserted}, 201)


async def device_sync(request: Request) -> Response:
    """设备数据同步入口（真实 Health Kit 适配层在此对接）。"""
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    db.execute(
        "UPDATE devices SET last_sync_at=? WHERE user_id=?",
        (db.now(), user_id),
    )
    await add_metrics(request)
    return _json({"ok": True, "synced_at": db.now(), "source": "device"})


async def list_metrics(request: Request) -> Response:
    params = request.query_params
    user_id = params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    rows = _metric_rows(user_id, params.get("type") or None, int(params.get("limit", 500)))
    return _json({"metrics": rows})


async def chat(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    message = (body.get("message") or "").strip()
    if not user_id or not message:
        return _json({"error": "缺少 user_id 或 message"}, 400)

    session_id = body.get("session_id")
    if session_id:
        session = db.query_one("SELECT * FROM symptom_sessions WHERE id=?", (session_id,))
        transcript = db.loads(session["transcript"], []) if session else []
    else:
        session_id = db.new_id("s_")
        transcript = []

    transcript.append({"role": "user", "text": message})
    # 分诊基于本段消息 + 会话历史（合并上下文更稳）
    full_text = " ".join(t["text"] for t in transcript if t["role"] == "user")

    # 组装用户上下文，供 LLM 生成个性化建议
    user = db.query_one("SELECT name, gender, birth_date, medical_history, allergies, current_medications FROM users WHERE id=?", (user_id,))
    user_context = {
        "name": user["name"] if user else None,
        "gender": user["gender"] if user else None,
        "age": user["birth_date"] if user else None,
        "medical_history": db.loads(user.get("medical_history"), []) if user else [],
        "allergies": db.loads(user.get("allergies"), []) if user else [],
        "current_medications": db.loads(user.get("current_medications"), []) if user else [],
    }
    result = triage.triage_with_llm(full_text, user_context)

    transcript.append({"role": "agent", "text": result["advice"]})
    notified = 0
    if result["notify"] in ("guardian", "immediate"):
        severity = "red" if result["level"] == "red" else "yellow"
        alerts.create_alert(
            user_id, severity=severity, type_="symptom",
            title=result["title"],
            message=result["advice"],
            channels=["in_app", "sms"] if severity == "red" else ["in_app"],
        )
        notified = 1

    db.execute(
        "INSERT OR REPLACE INTO symptom_sessions(id,user_id,started_at,ended_at,transcript,"
        "triage_level,extracted,advice,notified) VALUES(?,?,?,?,?,?,?,?,?)",
        (session_id, user_id, db.now(), db.now(), db.dumps(transcript),
         result["level"], db.dumps({"condition": result.get("matched_condition_id", "")}),
         result["advice"], notified),
    )

    return _json({
        "session_id": session_id,
        "triage_level": result["level"],
        "title": result["title"],
        "name": result["name"],
        "advice": result["advice"],
        "suggest_120": result["suggest_120"],
        "notify": result["notify"],
        "notified_guardian": bool(notified),
        "followups": result["followups"],
        "disclaimer": result["disclaimer"],
        "escalated": result["escalated"],
    })


async def sos(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    a = alerts.create_alert(
        user_id, severity="red", type_="sos",
        title="紧急呼救（SOS）",
        message="使用者触发了一键紧急呼救，请立即联系确认情况，必要时拨打 120。",
        channels=["in_app", "sms", "phone"],
    )
    return _json({"ok": True, "alert_id": a["id"], "status": "escalated"})


async def list_alerts(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    return _json({"alerts": alerts.list_alerts(user_id, int(request.query_params.get("limit", 50)))})


async def ack_alert(request: Request) -> Response:
    aid = request.path_params["id"]
    a = alerts.acknowledge(aid)
    if not a:
        return _json({"error": "告警不存在"}, 404)
    return _json({"ok": True, "alert": a})


async def list_reminders(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    due = {r["id"] for r in reminders.due_reminders(user_id)}
    rows = reminders.list_reminders(user_id)
    for r in rows:
        r["due_now"] = r["id"] in due
    return _json({"reminders": rows, "due": list(due)})


async def create_reminder(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    r = reminders.create_reminder(
        user_id, kind=body.get("kind", "medication"), title=body.get("title", "提醒"),
        detail=body.get("detail", ""), cron=body.get("cron", "08:00"),
        enabled=body.get("enabled", True))
    return _json({"ok": True, "reminder": r}, 201)


async def take_reminder(request: Request) -> Response:
    rid = request.path_params["id"]
    body = await _body(request)
    user_id = body.get("user_id", "")
    reminders.record_adherence(rid, user_id, bool(body.get("taken", True)), body.get("note", ""))
    return _json({"ok": True})


async def weekly_report(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"report": reports.generate_report(user_id, "weekly")})


async def monthly_report(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"report": reports.generate_report(user_id, "monthly")})


async def export_report(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    rtype = request.path_params["type"]
    if not user_id or rtype not in ("weekly", "monthly"):
        return _json({"error": "参数错误"}, 400)
    data = reports.export_report(user_id, rtype)
    return _json({"export": data})


async def guardian_dashboard(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    latest = _latest_metrics(user_id)
    latest_with_label = []
    for t, v in latest.items():
        ref = config.METRIC_REFERENCE.get(t, {})
        flag = None
        if ref and (v < ref["low"] or v > ref["high"]):
            flag = "high" if v > ref["high"] else "low"
        latest_with_label.append({
            "type": t, "label": ref.get("label", t), "unit": ref.get("unit", ""),
            "value": v, "flag": flag,
        })
    return _json({
        "user": user or {"id": user_id, "name": "未知"},
        "latest": latest_with_label,
        "alerts": alerts.list_alerts(user_id, 20),
        "unread": alerts.unread_count(user_id),
        "due_reminders": reminders.due_reminders(user_id),
        "series": {t: _series(user_id, t, 30) for t in latest},
    })


async def doctor_overview(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if user:
        for f in ("medical_history", "allergies", "current_medications"):
            user[f] = db.loads(user.get(f), [])
    weekly = reports.generate_report(user_id, "weekly")
    return _json({
        "user": user or {"id": user_id, "name": "未知"},
        "weekly": weekly,
        "series": {t: _series(user_id, t, 30) for t in _latest_metrics(user_id)},
    })


# ---------- 静态前端 ----------
def _html(page: str) -> FileResponse:
    return FileResponse(str(config.FRONTEND_DIR / page))


routes = [
    Route("/api/health", health),
    Route("/api/seed", do_seed, methods=["POST"]),
    Route("/api/users", list_users, methods=["GET"]),
    Route("/api/users", create_user, methods=["POST"]),
    Route("/api/users/{id}", get_user, methods=["GET"]),
    Route("/api/users/{id}", update_user, methods=["PUT"]),
    Route("/api/metrics", list_metrics, methods=["GET"]),
    Route("/api/metrics", add_metrics, methods=["POST"]),
    Route("/api/devices/sync", device_sync, methods=["POST"]),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/sos", sos, methods=["POST"]),
    Route("/api/alerts", list_alerts, methods=["GET"]),
    Route("/api/alerts/{id}/ack", ack_alert, methods=["POST"]),
    Route("/api/reminders", list_reminders, methods=["GET"]),
    Route("/api/reminders", create_reminder, methods=["POST"]),
    Route("/api/reminders/{id}/take", take_reminder, methods=["POST"]),
    Route("/api/reports/weekly", weekly_report, methods=["GET"]),
    Route("/api/reports/monthly", monthly_report, methods=["GET"]),
    Route("/api/reports/{type}/export", export_report, methods=["GET"]),
    Route("/api/guardian/dashboard", guardian_dashboard, methods=["GET"]),
    Route("/api/doctor/overview", doctor_overview, methods=["GET"]),
    Route("/", lambda _: _html("index.html")),
    Route("/user", lambda _: _html("user.html")),
    Route("/guardian", lambda _: _html("guardian.html")),
    Route("/doctor", lambda _: _html("doctor.html")),
]

app = Starlette(debug=False, routes=routes)
app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

# 启动时初始化数据库与调度器
db.get_conn()
reminders.start_scheduler()


def _open_browser() -> None:
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


if __name__ == "__main__":
    import uvicorn

    threading.Timer(1.0, _open_browser).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
