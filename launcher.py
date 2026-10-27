"""PyInstaller 打包入口：启动服务并打开浏览器。

打包方式（见 README）：
  pyinstaller --noconfirm --onefile --name MedAgent --add-data "app;app" \
    --add-data "frontend;frontend" --collect-all uvicorn --collect-all starlette \
    --hidden-import app.main launcher.py
"""
from __future__ import annotations

import threading
import webbrowser

import uvicorn

from app import config
from app.main import app


def _open_browser() -> None:
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
