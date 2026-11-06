"""全局配置。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    """读取项目根目录 .env（可选，零依赖）。已存在的环境变量优先。"""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

# 是否由 PyInstaller 打包（frozen）
_FROZEN = bool(getattr(sys, "frozen", False))

if _FROZEN:
    # 打包后资源在 sys._MEIPASS（只读），可写数据放到用户目录
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MedAgent"
else:
    # 项目根目录（app/ 的上一级）
    BASE_DIR = Path(__file__).resolve().parent.parent
    # 数据目录：存放 SQLite 数据库与知识库
    DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "medagent.db"

# 前端静态资源目录
FRONTEND_DIR = BASE_DIR / "frontend"

# 服务监听地址
HOST = os.environ.get("MEDAGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MEDAGENT_PORT", "8000"))

# 提醒调度轮询间隔（秒）
REMINDER_POLL_SECONDS = 15

# ============================================================
# AI 接入配置 —— 就在这里填写你的 API
# ============================================================
# 推荐方式：在项目根目录新建 .env 文件（不会提交到 git），写入：
#     DEEPSEEK_API_KEY=sk-你的key
#     DEEPSEEK_BASE_URL=https://api.deepseek.com
#     DEEPSEEK_MODEL=deepseek-chat
#
# 也可直接用任意 OpenAI 兼容服务，例如：
#     DEEPSEEK_BASE_URL=https://api.siliconflow.cn/v1
#     DEEPSEEK_MODEL=Qwen/Qwen2.5-7B-Instruct
#
# 不填写 Key 时，程序完全离线运行（纯本地规则引擎），不影响使用。
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 可选 AI 语音（OpenAI 兼容 TTS）；不配置则前端回退浏览器 Web Speech + 本地文本规范化。
AI_VOICE_API_KEY = os.environ.get("AI_VOICE_API_KEY", "")
AI_VOICE_BASE_URL = os.environ.get("AI_VOICE_BASE_URL", "https://api.openai.com/v1")
AI_TTS_MODEL = os.environ.get("AI_TTS_MODEL", "tts-1")
AI_TTS_VOICE = os.environ.get("AI_TTS_VOICE", "alloy")

# 指标参考区间（通用成人参考，非诊断标准，用于异常高亮）
METRIC_REFERENCE = {
    "heart_rate": {"label": "心率", "unit": "次/分", "low": 60, "high": 100},
    "blood_pressure_sys": {"label": "收缩压", "unit": "mmHg", "low": 90, "high": 140},
    "blood_pressure_dia": {"label": "舒张压", "unit": "mmHg", "low": 60, "high": 90},
    "blood_oxygen": {"label": "血氧", "unit": "%", "low": 95, "high": 100},
    "blood_glucose": {"label": "空腹血糖", "unit": "mmol/L", "low": 3.9, "high": 6.1},
    "temperature": {"label": "体温", "unit": "℃", "low": 36.0, "high": 37.3},
    "sleep_hours": {"label": "睡眠时长", "unit": "小时", "low": 6, "high": 9},
    "steps": {"label": "步数", "unit": "步", "low": 3000, "high": 20000},
    "weight": {"label": "体重", "unit": "kg", "low": 40, "high": 90},
}
