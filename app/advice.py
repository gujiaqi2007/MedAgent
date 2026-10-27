"""生活/饮食建议引擎：根据指标与用户病史生成报告建议（规则化，可溯源）。"""
from __future__ import annotations

from . import config


def _has_history(user: dict, *terms: str) -> bool:
    history = " ".join([str(user.get("medical_history", "") or ""),
                        str(user.get("current_medications", "") or "")])
    return any(t in history for t in terms)


def generate_advice(user: dict, latest: dict[str, float], anomalies: list[dict]) -> list[str]:
    """根据最新指标与异常项生成生活建议列表。

    user: 用户档案 dict；latest: {metric_type: 最新值}；anomalies: 异常项列表。
    """
    tips: list[str] = []

    # 血压
    sys_v = latest.get("blood_pressure_sys")
    dia_v = latest.get("blood_pressure_dia")
    if sys_v is not None or dia_v is not None:
        if (sys_v and sys_v >= 140) or (dia_v and dia_v >= 90):
            tips.append("血压偏高：建议低盐饮食（每日食盐不超过 5 克）、规律作息、按时服药，并坚持定时测量记录。")
        elif (sys_v and sys_v < 90) or (dia_v and dia_v < 60):
            tips.append("血压偏低：注意补水、起身缓慢，避免长时间站立；若伴头晕请及时就医。")
        else:
            tips.append("血压处于参考范围内，继续保持低盐饮食与规律测量。")

    # 血糖
    glu = latest.get("blood_glucose")
    if glu is not None:
        if glu > 6.1:
            tips.append("血糖偏高：建议控制主食与甜食，粗细粮搭配，规律用药，并增加餐后血糖监测。")
        elif glu < 3.9:
            tips.append("血糖偏低：注意规律进食，随身携带糖果以防低血糖；若反复发生请就医调整方案。")
        else:
            tips.append("血糖平稳，继续保持定时监测与均衡饮食。")

    # 心率
    hr = latest.get("heart_rate")
    if hr is not None:
        if hr > 100:
            tips.append("心率偏快：注意休息、避免情绪激动；若伴胸闷心慌请及时就医。")
        elif hr < 60:
            tips.append("心率偏慢：若长期如此且无不适可观察；若伴乏力、头晕请就医评估。")

    # 血氧
    spo2 = latest.get("blood_oxygen")
    if spo2 is not None and spo2 < 95:
        tips.append("血氧偏低：请注意休息，保持空气流通；若持续低于 95% 或伴呼吸困难，请立即就医。")

    # 睡眠
    sleep = latest.get("sleep_hours")
    if sleep is not None:
        if sleep < 6:
            tips.append("睡眠不足：建议固定作息、睡前远离电子屏幕，白天适量活动以改善睡眠。")
        elif sleep > 9:
            tips.append("睡眠偏多：建议保持白天适度活动，排查是否因乏力或情绪原因导致嗜睡。")

    # 步数
    steps = latest.get("steps")
    if steps is not None:
        if steps < 3000:
            tips.append("活动量偏低：建议在身体允许的前提下每日散步 20–30 分钟，循序渐进。")
        else:
            tips.append("活动量良好，继续保持规律运动。")

    # 体重
    weight = latest.get("weight")
    if weight is not None:
        if weight >= 90:
            tips.append("体重偏高：建议控制总热量、减少油炸与甜食，增加低强度有氧活动。")

    # 蛋白质摄入建议（结合病史/禁忌，避免与肾功能不全冲突）
    if any(a.get("type") in ("weight", "sleep_hours", "steps") for a in anomalies) or weight is not None:
        if _has_history(user, "肾", "肾功能不全", "肾病", "肾衰竭", "透析"):
            tips.append("蛋白质摄入请在医生/营养师指导下进行（结合肾功能情况），避免自行大量补充。")
        else:
            tips.append("建议保证优质蛋白质摄入，如鱼、蛋、奶、豆制品与瘦肉，有助于维持肌肉与体力。")

    if not tips:
        tips.append("各项指标总体平稳，请继续保持规律作息、均衡饮食与适度活动。")

    # 去重并保持顺序
    seen: set[str] = set()
    unique = [t for t in tips if not (t in seen or seen.add(t))]
    return unique
