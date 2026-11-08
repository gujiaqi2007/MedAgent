"""语音后处理：TTS 文本规范化（修复数字念法）+ 可选 AI 语音适配。

关键修复：
- 紧急号码 120/110/119 按位读作「幺二零 / 幺幺零 / 幺幺九」，而不是「一百二十」；
- 手机号逐位读；血压 120/80 读作「一百二十比八十」。

AI 语音：配置 AI_VOICE_API_KEY / AI_VOICE_BASE_URL 后，可调用 OpenAI 兼容的
/audio/speech 接口合成语音（见 ai_tts）；未配置则前端回退到浏览器 Web Speech + 本规范化。
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

from . import config

_CN_DIGITS = "零一二三四五六七八九"


def _num_to_cn(n: int) -> str:
    if n == 0:
        return "零"
    units = ["", "十", "百", "千"]
    s = str(n)
    out = ""
    for i, ch in enumerate(s):
        d = int(ch)
        u = len(s) - i - 1
        if d == 0:
            if out and not out.endswith("零"):
                out += "零"
            continue
        if u == 1 and d == 1 and i == 0:
            out += "十"
            continue
        out += _CN_DIGITS[d] + units[u]
    return out.rstrip("零") or "零"


def _bp(m: re.Match) -> str:
    a, b = int(m.group(1)), int(m.group(2))
    if 60 <= a <= 260 and 30 <= b <= 160:
        return f"{_num_to_cn(a)}比{_num_to_cn(b)}"
    return m.group(0)


def _phone(m: re.Match) -> str:
    return "".join("幺" if c == "1" else _CN_DIGITS[int(c)] for c in m.group(0))


def normalize_for_speech(text: str) -> str:
    """把文本转成更适合中文 TTS 朗读的形式。"""
    if not text:
        return ""
    t = str(text)
    # 血压 120/80 → 一百二十比八十
    t = re.sub(r"(\d{2,3})\s*/\s*(\d{2,3})", _bp, t)
    # 手机号逐位（1 读作幺）
    t = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", _phone, t)
    # 紧急/服务号码按位
    t = re.sub(r"(?<!\d)120(?!\d)", "幺二零", t)
    t = re.sub(r"(?<!\d)110(?!\d)", "幺幺零", t)
    t = re.sub(r"(?<!\d)119(?!\d)", "幺幺九", t)
    t = re.sub(r"(?<!\d)122(?!\d)", "幺二二", t)
    return t


def ai_tts(text: str) -> dict | None:
    """调用 OpenAI 兼容 TTS 合成语音。未配置或无网络时返回 None（前端回退）。"""
    if not config.AI_VOICE_API_KEY:
        return None
    payload = {
        "model": config.AI_TTS_MODEL,
        "input": normalize_for_speech(text),
        "voice": config.AI_TTS_VOICE,
        "response_format": "mp3",
    }
    req = urllib.request.Request(
        config.AI_VOICE_BASE_URL.rstrip("/") + "/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + config.AI_VOICE_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio = resp.read()
        return {"audio": base64.b64encode(audio).decode("ascii"), "mime": "audio/mpeg"}
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
