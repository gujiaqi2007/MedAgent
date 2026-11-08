"""产品功能静态数据与业务逻辑：慢病方案包、康复库、抑郁筛查、异常解读、设备预设。"""
from __future__ import annotations

import random
from datetime import datetime

CARE_PLANS = [
    {
        "id": "hypertension",
        "name": "高血压管理包",
        "chronic": "高血压",
        "reminders": [
            {"kind": "measurement", "title": "测量血压（晨起）", "detail": "静坐 5 分钟后测量并记录", "cron": "07:00"},
            {"kind": "medication", "title": "服用降压药", "detail": "按医嘱服药，不要自行停药", "cron": "08:00"},
        ],
        "tips": ["每日盐摄入 < 5 克", "固定时间测血压并记录", "规律作息、避免情绪激动"],
    },
    {
        "id": "diabetes",
        "name": "糖尿病管理包",
        "chronic": "糖尿病",
        "reminders": [
            {"kind": "measurement", "title": "空腹血糖", "detail": "早餐前测量", "cron": "07:00"},
            {"kind": "measurement", "title": "餐后血糖", "detail": "晚餐后 2 小时测量", "cron": "21:00"},
        ],
        "tips": ["控制主食与甜食", "定时监测血糖", "随身携带糖果防低血糖"],
    },
    {
        "id": "copd",
        "name": "慢阻肺管理包",
        "chronic": "慢阻肺",
        "reminders": [
            {"kind": "measurement", "title": "呼吸训练", "detail": "缩唇呼吸 10 分钟", "cron": "09:00"},
        ],
        "tips": ["戒烟、避免粉尘", "坚持呼吸训练", "注意保暖防感冒"],
    },
    {
        "id": "heart_failure",
        "name": "心衰管理包",
        "chronic": "心衰",
        "reminders": [
            {"kind": "measurement", "title": "晨起称体重", "detail": "固定时间、同样衣着", "cron": "07:00"},
        ],
        "tips": ["每日称重，体重骤增及时就医", "限盐限水", "遵医嘱服药"],
    },
]

REHAB_LIBRARY = [
    {
        "id": "joint_mobility", "name": "关节活动操", "duration": "10 分钟",
        "for": ["风湿", "关节炎", "关节", "腰", "背"],
        "steps": ["坐姿，缓慢屈伸膝关节 10 次", "脚踝画圈，正反各 10 次",
                  "扶稳站立，缓慢抬腿 5 次", "动作放缓，疼痛明显加重即停止"],
    },
    {
        "id": "breathing", "name": "缩唇呼吸训练", "duration": "10 分钟",
        "for": ["慢阻肺", "肺", "气短", "呼吸困难"],
        "steps": ["用鼻子缓慢吸气 2 秒", "缩唇像吹口哨一样呼气 4 秒",
                  "重复 10 次为一组，做 3 组", "出现头晕即停止"],
    },
    {
        "id": "balance", "name": "防跌倒平衡训练", "duration": "8 分钟",
        "for": ["跌倒", "平衡", "中风", "帕金森"],
        "steps": ["扶稳椅子，单脚站立 10 秒，左右交替", "脚跟对脚尖走直线 10 步",
                  "务必有家人陪同", "头晕或不稳即停止"],
    },
    {
        "id": "relax", "name": "降压放松操", "duration": "6 分钟",
        "for": ["高血压", "紧张", "焦虑", "失眠"],
        "steps": ["缓慢深呼吸 5 次", "依次放松肩颈、手臂、腿部", "闭眼静坐 2 分钟"],
    },
]

DEVICE_PRESETS = {
    "band": {"label": "智能手环", "metrics": [
        ("heart_rate", (66, 96), "次/分"), ("blood_oxygen", (95, 99), "%"),
        ("steps", (2000, 7000), "步"), ("sleep_hours", (5.5, 8.5), "小时")]},
    "bp_monitor": {"label": "电子血压计", "metrics": [
        ("blood_pressure_sys", (120, 155), "mmHg"), ("blood_pressure_dia", (75, 95), "mmHg")]},
    "glucose_meter": {"label": "血糖仪", "metrics": [("blood_glucose", (5.0, 8.0), "mmol/L")]},
    "scale": {"label": "体重 / 体脂秤", "metrics": [("weight", (60, 66), "kg")]},
    "oximeter": {"label": "血氧仪", "metrics": [("blood_oxygen", (94, 99), "%")]},
    "pill_box": {"label": "智能药盒", "metrics": []},
    "fall_detector": {"label": "跌倒检测雷达", "metrics": []},
}

DEPRESSION_QUESTIONS = [
    {"id": "q1", "text": "过去两周，您是否经常对做事提不起劲、没有兴趣？"},
    {"id": "q2", "text": "过去两周，您是否经常感到心情低落、沮丧或绝望？"},
]


def rehab_for(medical_history: list[str]) -> list[dict]:
    """按病史推荐康复动作。"""
    text = " ".join(medical_history or [])
    recommended = [r for r in REHAB_LIBRARY if any(k in text for k in r["for"])]
    return recommended or REHAB_LIBRARY[:2]


def score_depression(answers: list[int]) -> dict:
    score = sum(int(a) for a in answers if isinstance(a, (int, float)))
    if score >= 3:
        return {"score": score, "level": "high",
                "advice": "筛查提示可能存在抑郁情绪，建议尽快到精神心理科或老年科进一步评估（如 GDS-15 / PHQ-9）。"}
    if score >= 1:
        return {"score": score, "level": "moderate",
                "advice": "近期情绪偏低，建议多与家人朋友交流、规律作息与适度运动；若持续两周以上请就医。"}
    return {"score": score, "level": "low", "advice": "情绪状态良好，继续保持规律作息与社交活动。"}


ANOMALY_HINTS = {
    ("blood_pressure_sys", "high"): {
        "cause": "可能漏服降压药、情绪紧张、盐分摄入过多或睡眠不足。",
        "action": "静坐 15 分钟后复测；若仍偏高且伴头痛、胸闷或视物模糊，请尽快就医。"},
    ("blood_pressure_sys", "low"): {
        "cause": "可能饮水不足、起身过快或药物过量。", "action": "缓慢起身、适量补水；头晕明显请就医。"},
    ("blood_pressure_dia", "high"): {
        "cause": "可能血压控制不佳或情绪波动。", "action": "安静休息后复测，必要时联系医生调整用药。"},
    ("blood_glucose", "high"): {
        "cause": "可能饮食过量、漏用药或应激。", "action": "按医嘱用药、控制主食，2 小时后复测；持续偏高请就医。"},
    ("blood_glucose", "low"): {
        "cause": "可能进食不足或降糖药过量。", "action": "立即进食糖水/糖果并复测；意识不清请立即拨打 120。"},
    ("blood_oxygen", "low"): {
        "cause": "可能与肺部疾病、心功能或测量不当有关。", "action": "静息复测；若持续低于 95% 或伴呼吸困难，请立即就医。"},
    ("heart_rate", "high"): {
        "cause": "可能活动、情绪、发热或咖啡因。", "action": "静坐休息后复测；持续心慌请就医。"},
    ("heart_rate", "low"): {
        "cause": "可能与药物或传导问题有关。", "action": "若伴乏力、头晕，请就医评估。"},
    ("temperature", "high"): {
        "cause": "可能感染或炎症。", "action": "多喝温水、监测体温；高热不退请就医。"},
}


def interpret_anomaly(a: dict) -> dict:
    hint = ANOMALY_HINTS.get((a.get("type"), a.get("direction")))
    return hint or {"cause": "指标超出参考范围。", "action": "建议复测并咨询医生。"}


def simulate_readings(device_type: str) -> list[tuple]:
    """按设备类型生成模拟读数 (type, value, unit)。"""
    preset = DEVICE_PRESETS.get(device_type) or DEVICE_PRESETS["band"]
    out = []
    for mtype, (lo, hi), unit in preset["metrics"]:
        if isinstance(lo, float) or isinstance(hi, float):
            out.append((mtype, round(random.uniform(lo, hi), 1), unit))
        else:
            out.append((mtype, random.randint(lo, hi), unit))
    return out
