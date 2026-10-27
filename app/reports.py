"""周报/月报生成引擎：聚合指标 → 趋势/异常/生活建议 → 持久化与导出。"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import advice
from . import config
from . import database as db

DAYS = {"weekly": 7, "monthly": 30}
LABEL = {"weekly": "周报", "monthly": "月报"}


def _period_bounds(days: int) -> tuple[str, str, str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    return (
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
        prev_start.isoformat(timespec="seconds"),
        start.isoformat(timespec="seconds"),
    )


def _agg(user_id: str, start: str, end: str) -> dict[str, dict]:
    """聚合区间内各指标的统计量。"""
    rows = db.query(
        "SELECT type, value, measured_at FROM metrics "
        "WHERE user_id=? AND measured_at>=? AND measured_at<=? ORDER BY measured_at",
        (user_id, start, end),
    )
    out: dict[str, dict] = {}
    for r in rows:
        t = r["type"]
        v = r["value"]
        if t not in out:
            out[t] = {"values": [], "count": 0}
        out[t]["values"].append(v)
        out[t]["count"] += 1
    for t, d in out.items():
        vals = d["values"]
        d["latest"] = vals[-1]
        d["avg"] = round(sum(vals) / len(vals), 2)
        d["min"] = min(vals)
        d["max"] = max(vals)
    return out


def _detect_anomalies(agg: dict[str, dict]) -> list[dict]:
    """按参考区间标记异常。"""
    anomalies: list[dict] = []
    for t, ref in config.METRIC_REFERENCE.items():
        if t not in agg:
            continue
        latest = agg[t]["latest"]
        low, high = ref["low"], ref["high"]
        if latest < low or latest > high:
            anomalies.append({
                "type": t,
                "label": ref["label"],
                "unit": ref["unit"],
                "latest": latest,
                "reference": f"{low}–{high}",
                "direction": "high" if latest > high else "low",
            })
    return anomalies


def _trend(cur: dict, prev: dict) -> dict[str, str]:
    trends: dict[str, str] = {}
    for t in cur:
        if t not in prev:
            trends[t] = "新记录"
            continue
        delta = cur[t]["avg"] - prev[t]["avg"]
        if abs(delta) < 0.5:
            trends[t] = "平稳"
        elif delta > 0:
            trends[t] = "上升"
        else:
            trends[t] = "下降"
    return trends


def generate_report(user_id: str, report_type: str) -> dict:
    days = DAYS[report_type]
    start, end, prev_start, prev_end = _period_bounds(days)
    agg = _agg(user_id, start, end)
    prev_agg = _agg(user_id, prev_start, prev_end)
    anomalies = _detect_anomalies(agg)
    trends = _trend(agg, prev_agg)

    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    latest = {t: d["latest"] for t, d in agg.items()}
    tips = advice.generate_advice(user or {}, latest, anomalies)

    summary = {
        "report_type": report_type,
        "label": LABEL[report_type],
        "period_start": start,
        "period_end": end,
        "metric_count": len(agg),
        "anomaly_count": len(anomalies),
        "metrics": {
            t: {
                "label": config.METRIC_REFERENCE.get(t, {}).get("label", t),
                "unit": config.METRIC_REFERENCE.get(t, {}).get("unit", ""),
                "latest": d["latest"],
                "avg": d["avg"],
                "min": d["min"],
                "max": d["max"],
                "count": d["count"],
                "trend": trends.get(t, "平稳"),
            }
            for t, d in agg.items()
        },
    }

    report_id = db.new_id("r_")
    db.execute(
        "INSERT INTO reports(id,user_id,type,period_start,period_end,summary,anomalies,advice,generated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (report_id, user_id, report_type, start, end,
         db.dumps(summary), db.dumps(anomalies), db.dumps(tips), db.now()),
    )
    return {
        "id": report_id,
        "user_id": user_id,
        "summary": summary,
        "anomalies": anomalies,
        "advice": tips,
        "generated_at": db.now(),
    }


def export_report(user_id: str, report_type: str) -> dict:
    """导出结构化数据（接近 FHIR Observation 形态），可作为医生诊断凭据。"""
    report = generate_report(user_id, report_type)
    user = db.query_one("SELECT id,name,gender,birth_date,medical_history,allergies,current_medications FROM users WHERE id=?", (user_id,))
    observations = []
    for t, m in report["summary"]["metrics"].items():
        observations.append({
            "resourceType": "Observation",
            "code": t,
            "label": m["label"],
            "unit": m["unit"],
            "value": m["latest"],
            "period": {"start": report["summary"]["period_start"], "end": report["summary"]["period_end"]},
            "trend": m["trend"],
            "referenceRange": {
                "low": config.METRIC_REFERENCE.get(t, {}).get("low"),
                "high": config.METRIC_REFERENCE.get(t, {}).get("high"),
            },
        })
    return {
        "patient": user or {"id": user_id},
        "reportType": report_type,
        "period": {"start": report["summary"]["period_start"], "end": report["summary"]["period_end"]},
        "anomalies": report["anomalies"],
        "advice": report["advice"],
        "observations": observations,
        "disclaimer": "本数据为居家健康监测记录，供医生参考，不构成诊断。",
    }
