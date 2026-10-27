"""演示数据种子：一键生成可体验的示例使用者/监护人/医生/指标/提醒。"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import database as db

DEMO_USER_ID = "u_demo_zhang"
DEMO_GUARDIAN_ID = "g_demo_zhang"
DEMO_DOCTOR_ID = "d_demo_li"


def _insert_metrics(user_id: str) -> None:
    rng = random.Random(42)
    now = datetime.now().replace(second=0, microsecond=0)
    rows = []
    for i in range(30):
        day = now - timedelta(days=29 - i)
        # 心率
        rows.append((user_id, None, "heart_rate", rng.randint(68, 92), "次/分",
                     day.replace(hour=8).isoformat(), "device", "valid"))
        # 血压
        rows.append((user_id, None, "blood_pressure_sys", rng.randint(125, 152), "mmHg",
                     day.replace(hour=8).isoformat(), "device", "valid"))
        rows.append((user_id, None, "blood_pressure_dia", rng.randint(78, 95), "mmHg",
                     day.replace(hour=8).isoformat(), "device", "valid"))
        # 血氧
        rows.append((user_id, None, "blood_oxygen", round(rng.uniform(95, 99), 1), "%",
                     day.replace(hour=8).isoformat(), "device", "valid"))
        # 睡眠
        rows.append((user_id, None, "sleep_hours", round(rng.uniform(5.2, 8.5), 1), "小时",
                     day.replace(hour=7).isoformat(), "device", "valid"))
        # 步数
        rows.append((user_id, None, "steps", rng.randint(1800, 7600), "步",
                     day.replace(hour=21).isoformat(), "device", "valid"))
        # 血糖（隔天测）
        if i % 2 == 0:
            rows.append((user_id, None, "blood_glucose", round(rng.uniform(5.2, 7.4), 1), "mmol/L",
                         day.replace(hour=7).isoformat(), "manual", "valid"))
        # 体重（每 5 天）
        if i % 5 == 0:
            rows.append((user_id, None, "weight", round(rng.uniform(62, 65), 1), "kg",
                         day.replace(hour=7).isoformat(), "manual", "valid"))

    with db.get_conn():
        cur = db.get_conn().cursor()
        cur.executemany(
            "INSERT INTO metrics(user_id,device_id,type,value,unit,measured_at,source,quality) "
            "VALUES(?,?,?,?,?,?,?,?)", rows)
        db.get_conn().commit()


def seed_demo(force: bool = False) -> dict:
    """创建演示数据，返回演示对象 id。"""
    existing = db.query_one("SELECT id FROM users WHERE id=?", (DEMO_USER_ID,))
    if existing and not force:
        return {"user_id": DEMO_USER_ID, "guardian_id": DEMO_GUARDIAN_ID, "doctor_id": DEMO_DOCTOR_ID}

    db.execute(
        "INSERT OR REPLACE INTO users(id,name,gender,birth_date,height_cm,weight_kg,blood_type,"
        "medical_history,allergies,current_medications,phone,address,emergency_contacts,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (DEMO_USER_ID, "张奶奶", "女", "1954-03-12", 158, 63, "A",
         db.dumps(["高血压", "风湿性关节炎"]), db.dumps(["青霉素"]),
         db.dumps(["氨氯地平 5mg 每日一次", "塞来昔布 按需"]),
         "13800000001", "北京市朝阳区幸福小区 3-201",
         db.dumps([{"name": "张先生", "relation": "儿子", "phone": "13900000002"}]),
         db.now()),
    )
    db.execute(
        "INSERT OR REPLACE INTO guardians(id,user_id,name,phone,relation,is_primary,notify_channels,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (DEMO_GUARDIAN_ID, DEMO_USER_ID, "张先生", "13900000002", "儿子", 1,
         db.dumps(["in_app", "sms"]), db.now()),
    )
    db.execute(
        "INSERT OR REPLACE INTO doctors(id,name,hospital,specialty,created_at) VALUES(?,?,?,?,?)",
        (DEMO_DOCTOR_ID, "李医生", "社区医院", "全科/老年科", db.now()),
    )
    db.execute(
        "INSERT OR REPLACE INTO devices(id,user_id,vendor,model,device_external_id,bound_at,last_sync_at,status) "
        "VALUES(?,?,?,?,?,?,?,?)",
        ("dev_huawei_1", DEMO_USER_ID, "Huawei", "手环 8", "HW-BAND-0001", db.now(), db.now(), "active"),
    )
    _insert_metrics(DEMO_USER_ID)
    from . import reminders as rem
    rem.create_reminder(DEMO_USER_ID, kind="medication", title="服用氨氯地平 5mg",
                        detail="降压药，早餐后服用一片", cron="08:00")
    rem.create_reminder(DEMO_USER_ID, kind="measurement", title="测量血压",
                        detail="测量并记录收缩压/舒张压", cron="09:00")
    return {"user_id": DEMO_USER_ID, "guardian_id": DEMO_GUARDIAN_ID, "doctor_id": DEMO_DOCTOR_ID}
