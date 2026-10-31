"""全局配置。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 自动加载项目根目录下的 .env 文件（可选，未安装 python-dotenv 时静默跳过）
try:  # noqa: SIM105
    from dotenv import load_dotenv

    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(dotenv_path=_env_file, override=False)
except ImportError:
    pass

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

# 可选 LLM（DeepSeek / OpenAI 兼容）增强对话；不配置则走纯规则引擎，完全离线可用。
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

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
