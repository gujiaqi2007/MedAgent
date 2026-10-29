"""MedAgent 后端入口：Starlette 应用 + 路由 + 静态资源。

直接运行 `python -m app.main` 会启动 uvicorn 并自动打开浏览器（桌面式体验）。
"""
from __future__ import annotations

import json
import random
import threading
import webbrowser
from datetime import datetime, timedelta

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from . import alerts
from . import auth
from . import config
from . import database as db
from . import reminders
from . import reports
from . import seed as seed_mod
from . import triage
from . import voice


# ---------- 工具 ----------
def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, media_type="application/json; charset=utf-8")


async def _body(request: Request) -> dict:
    try:
        raw = await request.body()
        return json.loads(raw) if raw else {}
    except (ValueError, json.JSONDecodeError):
        return {}


def _auth(request: Request) -> dict | None:
    return auth.account_from_request(request)


def _deny(msg: str = "未登录或登录已过期", status: int = 401):
    return _json({"error": msg}, status)


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


# ---------- 鉴权 ----------
async def register(request: Request) -> Response:
    body = await _body(request)
    try:
        acct = auth.create_account(
            (body.get("username") or "").strip(), body.get("password", ""),
            body.get("role", "user"), body.get("display_name"),
        )
    except ValueError as e:
        return _json({"error": str(e)}, 400)
    if acct["role"] == "user":
        uid = db.new_id("u_")
        db.execute(
            "INSERT INTO users(id,name,created_at,account_id) VALUES(?,?,?,?)",
            (uid, acct.get("display_name") or acct["username"], db.now(), acct["id"]),
        )
        auth.bind(acct["id"], uid, "self")
    return _json({"ok": True, "account": auth._public(acct)}, 201)


async def login(request: Request) -> Response:
    body = await _body(request)
    acct = auth.verify_login(body.get("username", ""), body.get("password", ""))
    if not acct:
        return _json({"error": "用户名或密码错误"}, 401)
    token = auth.create_session(acct)
    return _json({"ok": True, "token": token, **auth.me_payload(acct)})


async def logout(request: Request) -> Response:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        auth.logout(h[7:].strip())
    return _json({"ok": True})


async def me(request: Request) -> Response:
    acct = _auth(request)
    if not acct:
        return _deny()
    return _json(auth.me_payload(acct))


async def bind_user(request: Request) -> Response:
    acct = _auth(request)
    if not acct:
        return _deny()
    if acct["role"] not in ("guardian", "doctor"):
        return _json({"error": "仅监护人/医生可绑定使用者"}, 403)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id or not db.query_one("SELECT id FROM users WHERE id=?", (user_id,)):
        return _json({"error": "使用者不存在"}, 404)
    if auth.can_access(acct, user_id):
        return _json({"ok": True, "already": True})
    auth.bind(acct["id"], user_id, acct["role"])
    return _json({"ok": True})


async def unbind_user(request: Request) -> Response:
    acct = _auth(request)
    if not acct:
        return _deny()
    body = await _body(request)
    db.execute("DELETE FROM bindings WHERE account_id=? AND user_id=?", (acct["id"], body.get("user_id")))
    return _json({"ok": True})


# ---------- 使用者 ----------
async def do_seed(request: Request) -> Response:
    body = await _body(request)
    result = seed_mod.seed_demo(force=bool(body.get("force", False)))
    return _json({"ok": True, **result})


async def list_users(request: Request) -> Response:
    acct = _auth(request)
    rows = db.query("SELECT id,name,gender,birth_date,phone,medical_history,allergies,current_medications,account_id FROM users")
    my_ids = set(auth.user_ids_for(acct)) if acct else set()
    for r in rows:
        r["medical_history"] = db.loads(r.get("medical_history"), [])
        r["allergies"] = db.loads(r.get("allergies"), [])
        r["current_medications"] = db.loads(r.get("current_medications"), [])
        r["bound"] = r["id"] in my_ids
    return _json({"users": rows})


async def get_user(request: Request) -> Response:
    acct = _auth(request)
    uid = request.path_params["id"]
    if acct and not auth.can_access(acct, uid):
        return _json({"error": "无权访问该使用者"}, 403)
    row = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not row:
        return _json({"error": "用户不存在"}, 404)
    for f in ("medical_history", "allergies", "current_medications", "emergency_contacts"):
        row[f] = db.loads(row.get(f), [])
    row["guardians"] = db.query("SELECT * FROM guardians WHERE user_id=?", (uid,))
    row["accounts"] = auth.accounts_for_user(uid)
    return _json({"user": row})


async def create_user(request: Request) -> Response:
    acct = _auth(request)
    body = await _body(request)
    uid = db.new_id("u_")
    name = body.get("name") or "未命名使用者"
    db.execute(
        "INSERT INTO users(id,name,gender,birth_date,height_cm,weight_kg,blood_type,"
        "medical_history,allergies,current_medications,phone,address,emergency_contacts,created_at,account_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, name, body.get("gender"), body.get("birth_date"), body.get("height_cm"),
         body.get("weight_kg"), body.get("blood_type"),
         db.dumps(body.get("medical_history", [])), db.dumps(body.get("allergies", [])),
         db.dumps(body.get("current_medications", [])), body.get("phone"), body.get("address"),
         db.dumps(body.get("emergency_contacts", [])), db.now(), None),
    )
    if acct and acct["role"] == "user":
        auth.bind(acct["id"], uid, "self")
    return _json({"ok": True, "user_id": uid}, 201)


async def update_user(request: Request) -> Response:
    acct = _auth(request)
    uid = request.path_params["id"]
    if acct and not auth.can_access(acct, uid):
        return _json({"error": "无权修改该使用者"}, 403)
    body = await _body(request)
    fields = ["name", "gender", "birth_date", "height_cm", "weight_kg", "blood_type", "phone", "address"]
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


# ---------- 指标 ----------
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


async def list_metrics(request: Request) -> Response:
    params = request.query_params
    user_id = params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    if params.get("type"):
        rows = db.query(
            "SELECT * FROM metrics WHERE user_id=? AND type=? ORDER BY measured_at DESC LIMIT ?",
            (user_id, params["type"], int(params.get("limit", 500))),
        )
    else:
        rows = db.query(
            "SELECT * FROM metrics WHERE user_id=? ORDER BY measured_at DESC LIMIT ?",
            (user_id, int(params.get("limit", 500))),
        )
    return _json({"metrics": rows})


# ---------- 设备（可穿戴同步） ----------
async def list_devices(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"devices": db.query("SELECT * FROM devices WHERE user_id=?", (user_id,))})


async def sync_device(request: Request) -> Response:
    """设备数据同步：支持真实推送（metrics）或模拟拉取（simulate）。

    真实厂商（华为 Health Kit / Apple Health / 小米 / Health Connect）在适配层调用本接口。
    """
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    dev = db.query_one(
        "SELECT * FROM devices WHERE user_id=? AND status='active' ORDER BY bound_at DESC LIMIT 1",
        (user_id,),
    )
    device_id = body.get("device_id") or (dev["id"] if dev else None)
    inserted = 0
    if body.get("metrics"):
        for m in body["metrics"]:
            if m.get("type") and m.get("value") is not None:
                ref = config.METRIC_REFERENCE.get(m["type"], {})
                db.execute(
                    "INSERT INTO metrics(user_id,device_id,type,value,unit,measured_at,source,quality) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, device_id, m["type"], float(m["value"]),
                     m.get("unit") or ref.get("unit", ""),
                     m.get("measured_at") or db.now(), "device", "valid"),
                )
                inserted += 1
    elif body.get("simulate", True):
        rng = random.Random()
        now = datetime.now().replace(second=0, microsecond=0)
        samples = [("heart_rate", rng.randint(66, 96), "次/分"),
                   ("blood_oxygen", round(rng.uniform(95, 99), 1), "%")]
        samples.append(("steps", rng.randint(2000, 7000), "步"))
        for t, v, u in samples:
            db.execute(
                "INSERT INTO metrics(user_id,device_id,type,value,unit,measured_at,source,quality) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (user_id, device_id, t, v, u, now.isoformat(), "device", "valid"),
            )
            inserted += 1
    if dev:
        db.execute("UPDATE devices SET last_sync_at=? WHERE id=?", (db.now(), dev["id"]))
    return _json({"ok": True, "inserted": inserted, "synced_at": db.now(), "device": dev})


# ---------- 对话分诊 ----------
async def chat(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    message = (body.get("message") or "").strip()
    if not user_id or not message:
        return _json({"error": "缺少 user_id 或 message"}, 400)

    session_id = body.get("session_id")
    transcript = []
    if session_id:
        session = db.query_one("SELECT * FROM symptom_sessions WHERE id=?", (session_id,))
        if session:
            transcript = db.loads(session["transcript"], [])

    transcript.append({"role": "user", "text": message})
    full_text = " ".join(t["text"] for t in transcript if t["role"] == "user")
    result = triage.triage(full_text)
    transcript.append({"role": "agent", "text": result["advice"]})

    notified = 0
    if result["notify"] in ("guardian", "immediate"):
        severity = "red" if result["level"] == "red" else "yellow"
        alerts.create_alert(
            user_id, severity=severity, type_="symptom",
            title=result["title"], message=result["advice"],
            channels=["in_app", "sms"] if severity == "red" else ["in_app"],
        )
        notified = 1

    if not session_id:
        session_id = db.new_id("s_")
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
        "plain": result.get("plain", ""),
        "advice": result["advice"],
        "source": result.get("source", ""),
        "suggest_120": result["suggest_120"],
        "notify": result["notify"],
        "notified_guardian": bool(notified),
        "followups": result["followups"],
        "disclaimer": result["disclaimer"],
        "escalated": result["escalated"],
    })


# ---------- 告警 / SOS ----------
async def sos(request: Request) -> Response:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    a = alerts.create_alert(
        user_id, severity="red", type_="sos", title="紧急呼救（SOS）",
        message="使用者触发了一键紧急呼救，请立即联系确认情况，必要时拨打 120。",
        channels=["in_app", "sms", "phone"],
    )
    return _json({"ok": True, "alert_id": a["id"], "status": "escalated"})


async def list_alerts(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    return _json({"alerts": alerts.list_alerts(user_id, int(request.query_params.get("limit", 50)))})


async def ack_alert(request: Request) -> Response:
    a = alerts.acknowledge(request.path_params["id"])
    if not a:
        return _json({"error": "告警不存在"}, 404)
    return _json({"ok": True, "alert": a})


# ---------- 提醒 / 日程 ----------
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
    acct = _auth(request)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    if acct and not auth.can_access(acct, user_id):
        return _json({"error": "无权为该使用者设置日程"}, 403)
    r = reminders.create_reminder(
        user_id, kind=body.get("kind", "medication"), title=body.get("title", "提醒"),
        detail=body.get("detail", ""), cron=body.get("cron", "08:00"),
        enabled=body.get("enabled", True))
    return _json({"ok": True, "reminder": r}, 201)


async def update_reminder(request: Request) -> Response:
    acct = _auth(request)
    rid = request.path_params["id"]
    rem = db.query_one("SELECT * FROM reminders WHERE id=?", (rid,))
    if not rem:
        return _json({"error": "提醒不存在"}, 404)
    if acct and not auth.can_access(acct, rem["user_id"]):
        return _json({"error": "无权修改该日程"}, 403)
    body = await _body(request)
    sets, params = [], []
    for f in ("title", "detail", "cron", "kind"):
        if f in body:
            sets.append(f"{f}=?")
            params.append(body[f])
    if "enabled" in body:
        sets.append("enabled=?")
        params.append(1 if body["enabled"] else 0)
    if not sets:
        return _json({"ok": False, "error": "无可更新字段"}, 400)
    params.append(rid)
    db.execute(f"UPDATE reminders SET {', '.join(sets)} WHERE id=?", tuple(params))
    return _json({"ok": True, "reminder": db.query_one("SELECT * FROM reminders WHERE id=?", (rid,))})


async def delete_reminder(request: Request) -> Response:
    acct = _auth(request)
    rid = request.path_params["id"]
    rem = db.query_one("SELECT * FROM reminders WHERE id=?", (rid,))
    if not rem:
        return _json({"error": "提醒不存在"}, 404)
    if acct and not auth.can_access(acct, rem["user_id"]):
        return _json({"error": "无权删除该日程"}, 403)
    db.execute("DELETE FROM reminders WHERE id=?", (rid,))
    return _json({"ok": True})


async def take_reminder(request: Request) -> Response:
    rid = request.path_params["id"]
    body = await _body(request)
    reminders.record_adherence(rid, body.get("user_id", ""), bool(body.get("taken", True)), body.get("note", ""))
    return _json({"ok": True})


# ---------- 医嘱（医生） ----------
async def list_orders(request: Request) -> Response:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"orders": db.query("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (user_id,))})


async def create_order(request: Request) -> Response:
    acct = _auth(request)
    if not acct:
        return _deny()
    if acct["role"] != "doctor":
        return _json({"error": "仅医生可开具医嘱"}, 403)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id or not auth.can_access(acct, user_id):
        return _json({"error": "无权为该使用者开具医嘱"}, 403)
    doctor_row = db.query_one("SELECT id FROM doctors WHERE account_id=?", (acct["id"],))
    oid = db.new_id("o_")
    db.execute(
        "INSERT INTO orders(id,user_id,doctor_id,title,medication,dosage,frequency,duration_days,"
        "instructions,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (oid, user_id, doctor_row["id"] if doctor_row else None,
         body.get("title", "医嘱"), body.get("medication", ""), body.get("dosage", ""),
         body.get("frequency", ""), body.get("duration_days"), body.get("instructions", ""),
         "active", db.now()),
    )
    cron = body.get("cron") or "08:00"
    reminders.create_reminder(
        user_id, kind="medication", title=body.get("title", "医嘱用药"),
        detail=f"{body.get('medication','')} {body.get('dosage','')} {body.get('frequency','')}".strip(),
        cron=cron,
    )
    return _json({"ok": True, "order": db.query_one("SELECT * FROM orders WHERE id=?", (oid,))}, 201)


async def stop_order(request: Request) -> Response:
    acct = _auth(request)
    oid = request.path_params["id"]
    order = db.query_one("SELECT * FROM orders WHERE id=?", (oid,))
    if not order:
        return _json({"error": "医嘱不存在"}, 404)
    if acct and not auth.can_access(acct, order["user_id"]):
        return _json({"error": "无权操作"}, 403)
    db.execute("UPDATE orders SET status='stopped', stopped_at=? WHERE id=?", (db.now(), oid))
    return _json({"ok": True})


# ---------- 报告 ----------
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
    return _json({"export": reports.export_report(user_id, rtype)})


# ---------- 仪表盘 ----------
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
        latest_with_label.append({"type": t, "label": ref.get("label", t),
                                  "unit": ref.get("unit", ""), "value": v, "flag": flag})
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
        "orders": db.query("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (user_id,)),
        "series": {t: _series(user_id, t, 30) for t in _latest_metrics(user_id)},
    })


# ---------- 语音 ----------
async def voice_normalize(request: Request) -> Response:
    body = await _body(request)
    text = body.get("text", "")
    return _json({"original": text, "normalized": voice.normalize_for_speech(text)})


async def voice_tts(request: Request) -> Response:
    body = await _body(request)
    result = voice.ai_tts(body.get("text", ""))
    if not result:
        return _json({"error": "未配置 AI 语音服务，前端请使用浏览器语音", "fallback": True}, 501)
    return _json(result)


# ---------- 静态前端 ----------
def _html(page: str) -> FileResponse:
    return FileResponse(str(config.FRONTEND_DIR / page))


routes = [
    Route("/api/health", lambda r: _json({"status": "ok", "service": "MedAgent", "time": db.now()})),
    Route("/api/seed", do_seed, methods=["POST"]),

    Route("/api/auth/register", register, methods=["POST"]),
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/bind", bind_user, methods=["POST"]),
    Route("/api/unbind", unbind_user, methods=["POST"]),

    Route("/api/users", list_users, methods=["GET"]),
    Route("/api/users", create_user, methods=["POST"]),
    Route("/api/users/{id}", get_user, methods=["GET"]),
    Route("/api/users/{id}", update_user, methods=["PUT"]),

    Route("/api/metrics", list_metrics, methods=["GET"]),
    Route("/api/metrics", add_metrics, methods=["POST"]),
    Route("/api/devices", list_devices, methods=["GET"]),
    Route("/api/devices/sync", sync_device, methods=["POST"]),

    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/sos", sos, methods=["POST"]),

    Route("/api/alerts", list_alerts, methods=["GET"]),
    Route("/api/alerts/{id}/ack", ack_alert, methods=["POST"]),

    Route("/api/reminders", list_reminders, methods=["GET"]),
    Route("/api/reminders", create_reminder, methods=["POST"]),
    Route("/api/reminders/{id}", update_reminder, methods=["PUT"]),
    Route("/api/reminders/{id}", delete_reminder, methods=["DELETE"]),
    Route("/api/reminders/{id}/take", take_reminder, methods=["POST"]),

    Route("/api/orders", list_orders, methods=["GET"]),
    Route("/api/orders", create_order, methods=["POST"]),
    Route("/api/orders/{id}/stop", stop_order, methods=["POST"]),

    Route("/api/reports/weekly", weekly_report, methods=["GET"]),
    Route("/api/reports/monthly", monthly_report, methods=["GET"]),
    Route("/api/reports/{type}/export", export_report, methods=["GET"]),

    Route("/api/guardian/dashboard", guardian_dashboard, methods=["GET"]),
    Route("/api/doctor/overview", doctor_overview, methods=["GET"]),

    Route("/api/voice/normalize", voice_normalize, methods=["POST"]),
    Route("/api/voice/tts", voice_tts, methods=["POST"]),

    Route("/", lambda _: _html("index.html")),
    Route("/login", lambda _: _html("login.html")),
    Route("/user", lambda _: _html("user.html")),
    Route("/guardian", lambda _: _html("guardian.html")),
    Route("/doctor", lambda _: _html("doctor.html")),
]

app = Starlette(debug=False, routes=routes)
app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

db.get_conn()
reminders.start_scheduler()


def _open_browser() -> None:
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


if __name__ == "__main__":
    import uvicorn
    threading.Timer(1.0, _open_browser).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
