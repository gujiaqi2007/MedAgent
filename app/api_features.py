"""产品功能扩展接口：护理任务、图文问诊、随访、签约、慢病方案、康复、筛查、多设备、异常解读。"""
from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import auth
from . import config
from . import database as db
from . import features
from . import reminders


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


def _require_access(request: Request, user_id: str):
    """返回 (account, error_response)。account 为空或无权时 error_response 非空。"""
    acct = _auth(request)
    if not acct:
        return None, _deny()
    if not auth.can_access(acct, user_id):
        return None, _json({"error": "无权访问该使用者"}, 403)
    return acct, None


# ---------- 护理任务清单 ----------
async def list_care_tasks(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"tasks": db.query(
        "SELECT * FROM care_tasks WHERE user_id=? ORDER BY status, created_at DESC", (user_id,))})


async def create_care_task(request: Request) -> JSONResponse:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    _, err = _require_access(request, user_id)
    if err:
        return err
    tid = db.new_id("ct_")
    db.execute(
        "INSERT INTO care_tasks(id,user_id,title,detail,assignee,status,due_date,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (tid, user_id, body.get("title", "护理任务"), body.get("detail", ""),
         body.get("assignee", ""), "todo", body.get("due_date"), db.now()),
    )
    return _json({"ok": True, "task": db.query_one("SELECT * FROM care_tasks WHERE id=?", (tid,))}, 201)


async def done_care_task(request: Request) -> JSONResponse:
    tid = request.path_params["id"]
    task = db.query_one("SELECT * FROM care_tasks WHERE id=?", (tid,))
    if not task:
        return _json({"error": "任务不存在"}, 404)
    _, err = _require_access(request, task["user_id"])
    if err:
        return err
    db.execute("UPDATE care_tasks SET status='done' WHERE id=?", (tid,))
    return _json({"ok": True})


async def delete_care_task(request: Request) -> JSONResponse:
    tid = request.path_params["id"]
    task = db.query_one("SELECT * FROM care_tasks WHERE id=?", (tid,))
    if not task:
        return _json({"error": "任务不存在"}, 404)
    _, err = _require_access(request, task["user_id"])
    if err:
        return err
    db.execute("DELETE FROM care_tasks WHERE id=?", (tid,))
    return _json({"ok": True})


# ---------- 图文问诊 ----------
async def list_consultations(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    _, err = _require_access(request, user_id)
    if err:
        return err
    return _json({"consultations": db.query(
        "SELECT * FROM consultations WHERE user_id=? ORDER BY created_at DESC", (user_id,))})


async def create_consultation(request: Request) -> JSONResponse:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    acct, err = _require_access(request, user_id)
    if err:
        return err
    cid = db.new_id("c_")
    db.execute(
        "INSERT INTO consultations(id,user_id,account_id,subject,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (cid, user_id, acct["id"], body.get("subject", "健康咨询"), "pending", db.now(), db.now()),
    )
    if body.get("message"):
        db.execute(
            "INSERT INTO consultation_messages(consultation_id,role,text,created_at) VALUES(?,?,?,?)",
            (cid, "user", body["message"], db.now()),
        )
    return _json({"ok": True, "consultation_id": cid}, 201)


async def get_consultation(request: Request) -> JSONResponse:
    cid = request.path_params["id"]
    c = db.query_one("SELECT * FROM consultations WHERE id=?", (cid,))
    if not c:
        return _json({"error": "问诊不存在"}, 404)
    _, err = _require_access(request, c["user_id"])
    if err:
        return err
    msgs = db.query("SELECT * FROM consultation_messages WHERE consultation_id=? ORDER BY id", (cid,))
    return _json({"consultation": c, "messages": msgs})


async def reply_consultation(request: Request) -> JSONResponse:
    cid = request.path_params["id"]
    c = db.query_one("SELECT * FROM consultations WHERE id=?", (cid,))
    if not c:
        return _json({"error": "问诊不存在"}, 404)
    acct, err = _require_access(request, c["user_id"])
    if err:
        return err
    body = await _body(request)
    role = "doctor" if acct["role"] == "doctor" else "user"
    db.execute(
        "INSERT INTO consultation_messages(consultation_id,role,text,created_at) VALUES(?,?,?,?)",
        (cid, role, body.get("text", ""), db.now()),
    )
    status = "replied" if role == "doctor" else "pending"
    db.execute("UPDATE consultations SET status=?, updated_at=? WHERE id=?", (status, db.now(), cid))
    return _json({"ok": True})


async def close_consultation(request: Request) -> JSONResponse:
    cid = request.path_params["id"]
    c = db.query_one("SELECT * FROM consultations WHERE id=?", (cid,))
    if not c:
        return _json({"error": "问诊不存在"}, 404)
    _, err = _require_access(request, c["user_id"])
    if err:
        return err
    db.execute("UPDATE consultations SET status='closed', updated_at=? WHERE id=?", (db.now(), cid))
    return _json({"ok": True})


# ---------- 随访 / 签约 ----------
async def list_followups(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"followups": db.query(
        "SELECT * FROM followups WHERE user_id=? ORDER BY next_date", (user_id,))})


async def create_followup(request: Request) -> JSONResponse:
    acct = _auth(request)
    if not acct:
        return _deny()
    if acct["role"] != "doctor":
        return _json({"error": "仅医生可创建随访"}, 403)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id or not auth.can_access(acct, user_id):
        return _json({"error": "无权为该使用者创建随访"}, 403)
    fid = db.new_id("fu_")
    db.execute(
        "INSERT INTO followups(id,user_id,doctor_account_id,title,plan,next_date,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (fid, user_id, acct["id"], body.get("title", "定期随访"), body.get("plan", ""),
         body.get("next_date"), "active", db.now()),
    )
    return _json({"ok": True, "followup": db.query_one("SELECT * FROM followups WHERE id=?", (fid,))}, 201)


async def update_followup(request: Request) -> JSONResponse:
    fid = request.path_params["id"]
    fu = db.query_one("SELECT * FROM followups WHERE id=?", (fid,))
    if not fu:
        return _json({"error": "随访不存在"}, 404)
    _, err = _require_access(request, fu["user_id"])
    if err:
        return err
    body = await _body(request)
    sets, params = [], []
    for f in ("title", "plan", "next_date", "status"):
        if f in body:
            sets.append(f"{f}=?")
            params.append(body[f])
    if not sets:
        return _json({"ok": False, "error": "无可更新字段"}, 400)
    params.append(fid)
    db.execute(f"UPDATE followups SET {', '.join(sets)} WHERE id=?", tuple(params))
    return _json({"ok": True})


async def create_signing(request: Request) -> JSONResponse:
    acct = _auth(request)
    if not acct:
        return _deny()
    if acct["role"] != "doctor":
        return _json({"error": "仅医生可签约"}, 403)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id or not auth.can_access(acct, user_id):
        return _json({"error": "无权签约该使用者"}, 403)
    existing = db.query_one("SELECT id FROM signings WHERE user_id=? AND doctor_account_id=?", (user_id, acct["id"]))
    if existing:
        return _json({"ok": True, "already": True})
    sid = db.new_id("sg_")
    db.execute("INSERT INTO signings(id,user_id,doctor_account_id,status,signed_at) VALUES(?,?,?,?,?)",
               (sid, user_id, acct["id"], "active", db.now()))
    return _json({"ok": True, "signing_id": sid}, 201)


async def list_signings(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"signings": db.query("SELECT * FROM signings WHERE user_id=?", (user_id,))})


# ---------- 慢病方案包 ----------
async def list_care_plans(_: Request) -> JSONResponse:
    return _json({"plans": features.CARE_PLANS})


async def apply_care_plan(request: Request) -> JSONResponse:
    plan_id = request.path_params["id"]
    plan = next((p for p in features.CARE_PLANS if p["id"] == plan_id), None)
    if not plan:
        return _json({"error": "方案不存在"}, 404)
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    _, err = _require_access(request, user_id)
    if err:
        return err
    created = []
    for r in plan["reminders"]:
        row = reminders.create_reminder(
            user_id, kind=r["kind"], title=r["title"], detail=r["detail"], cron=r["cron"])
        created.append(row["id"])
    db.execute("INSERT INTO plan_applications(id,user_id,plan_id,applied_at) VALUES(?,?,?,?)",
               (db.new_id("pa_"), user_id, plan_id, db.now()))
    return _json({"ok": True, "created_reminders": created, "tips": plan["tips"]}, 201)


# ---------- 康复指导 ----------
async def rehab_guide(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    history = db.loads(user.get("medical_history"), []) if user else []
    return _json({"items": features.rehab_for(history)})


# ---------- 心理 / 抑郁筛查 ----------
async def depression_questions(_: Request) -> JSONResponse:
    return _json({"questions": features.DEPRESSION_QUESTIONS})


async def submit_depression(request: Request) -> JSONResponse:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    _, err = _require_access(request, user_id)
    if err:
        return err
    result = features.score_depression(body.get("answers", []))
    aid = db.new_id("as_")
    db.execute(
        "INSERT INTO assessments(id,user_id,type,score,level,advice,created_at) VALUES(?,?,?,?,?,?,?)",
        (aid, user_id, "depression", result["score"], result["level"], result["advice"], db.now()),
    )
    return _json({"ok": True, "result": result, "assessment_id": aid}, 201)


async def list_assessments(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    return _json({"assessments": db.query(
        "SELECT * FROM assessments WHERE user_id=? ORDER BY created_at DESC", (user_id,))})


# ---------- 多设备接入 ----------
async def register_device(request: Request) -> JSONResponse:
    body = await _body(request)
    user_id = body.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    _, err = _require_access(request, user_id)
    if err:
        return err
    dtype = body.get("device_type", "band")
    preset = features.DEVICE_PRESETS.get(dtype)
    if not preset:
        return _json({"error": "不支持的设备类型"}, 400)
    did = db.new_id("dev_")
    db.execute(
        "INSERT INTO devices(id,user_id,vendor,model,device_external_id,bound_at,last_sync_at,status,device_type) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (did, user_id, body.get("vendor", "通用"), body.get("model") or preset["label"],
         body.get("device_external_id"), db.now(), None, "active", dtype),
    )
    return _json({"ok": True, "device": db.query_one("SELECT * FROM devices WHERE id=?", (did,))}, 201)


async def sync_device_by_id(request: Request) -> JSONResponse:
    did = request.path_params["id"]
    dev = db.query_one("SELECT * FROM devices WHERE id=?", (did,))
    if not dev:
        return _json({"error": "设备不存在"}, 404)
    _, err = _require_access(request, dev["user_id"])
    if err:
        return err
    dtype = dev.get("device_type") or "band"
    readings = features.simulate_readings(dtype)
    now = db.now()
    for mtype, value, unit in readings:
        db.execute(
            "INSERT INTO metrics(user_id,device_id,type,value,unit,measured_at,source,quality) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (dev["user_id"], did, mtype, value, unit, now, "device", "valid"),
        )
    db.execute("UPDATE devices SET last_sync_at=? WHERE id=?", (now, did))
    return _json({"ok": True, "inserted": len(readings), "synced_at": now,
                  "device_type": dtype, "device": dev})


# ---------- 异常解读 ----------
async def anomaly_insights(request: Request) -> JSONResponse:
    user_id = request.query_params.get("user_id")
    if not user_id:
        return _json({"error": "缺少 user_id"}, 400)
    rows = db.query(
        "SELECT type, value FROM metrics WHERE user_id=? AND id IN "
        "(SELECT MAX(id) FROM metrics WHERE user_id=? GROUP BY type)",
        (user_id, user_id),
    )
    out = []
    for r in rows:
        ref = config.METRIC_REFERENCE.get(r["type"])
        if not ref:
            continue
        v = r["value"]
        if v > ref["high"] or v < ref["low"]:
            direction = "high" if v > ref["high"] else "low"
            hint = features.interpret_anomaly({"type": r["type"], "direction": direction})
            out.append({"type": r["type"], "label": ref["label"], "unit": ref["unit"],
                        "value": v, "reference": f"{ref['low']}–{ref['high']}",
                        "direction": direction, **hint})
    return _json({"insights": out})


# ---------- 医生：批量患者（异常优先） ----------
async def patient_list(request: Request) -> JSONResponse:
    acct = _auth(request)
    if not acct:
        return _deny()
    users = db.query("SELECT id,name,medical_history FROM users")
    bound = set(auth.user_ids_for(acct))
    result = []
    for u in users:
        if bound and u["id"] not in bound:
            continue
        latest = db.query(
            "SELECT type, value FROM metrics WHERE user_id=? AND id IN "
            "(SELECT MAX(id) FROM metrics WHERE user_id=? GROUP BY type)",
            (u["id"], u["id"]),
        )
        anomalies = 0
        for r in latest:
            ref = config.METRIC_REFERENCE.get(r["type"])
            if ref and (r["value"] > ref["high"] or r["value"] < ref["low"]):
                anomalies += 1
        result.append({
            "user_id": u["id"], "name": u["name"],
            "medical_history": db.loads(u.get("medical_history"), []),
            "anomalies": anomalies, "bound": u["id"] in bound,
        })
    result.sort(key=lambda x: (-x["anomalies"], x["name"]))
    return _json({"patients": result})


feature_routes = [
    # 护理任务
    ("/api/care-tasks", list_care_tasks, ["GET"]),
    ("/api/care-tasks", create_care_task, ["POST"]),
    ("/api/care-tasks/{id}/done", done_care_task, ["POST"]),
    ("/api/care-tasks/{id}", delete_care_task, ["DELETE"]),
    # 图文问诊
    ("/api/consultations", list_consultations, ["GET"]),
    ("/api/consultations", create_consultation, ["POST"]),
    ("/api/consultations/{id}", get_consultation, ["GET"]),
    ("/api/consultations/{id}/messages", reply_consultation, ["POST"]),
    ("/api/consultations/{id}/close", close_consultation, ["POST"]),
    # 随访 / 签约
    ("/api/followups", list_followups, ["GET"]),
    ("/api/followups", create_followup, ["POST"]),
    ("/api/followups/{id}", update_followup, ["PUT"]),
    ("/api/signings", create_signing, ["POST"]),
    ("/api/signings", list_signings, ["GET"]),
    # 慢病方案
    ("/api/care-plans", list_care_plans, ["GET"]),
    ("/api/care-plans/{id}/apply", apply_care_plan, ["POST"]),
    # 康复 / 筛查
    ("/api/rehab", rehab_guide, ["GET"]),
    ("/api/assessments/depression/questions", depression_questions, ["GET"]),
    ("/api/assessments/depression", submit_depression, ["POST"]),
    ("/api/assessments", list_assessments, ["GET"]),
    # 多设备
    ("/api/devices/register", register_device, ["POST"]),
    ("/api/devices/{id}/sync", sync_device_by_id, ["POST"]),
    # 异常解读 / 患者列表
    ("/api/anomaly-insights", anomaly_insights, ["GET"]),
    ("/api/patients", patient_list, ["GET"]),
]
