# 健康守护 Agent（MedAgent）

面向特殊人群（老年人、长期疾病患者等）的**主动式健康管理 Agent**。
本地可安装、离线可用的桌面式应用：Python 后端 + 极简 Web 前端，双击即可启动。

> ⚠️ 本应用为健康管理辅助工具，**不构成医疗诊断**。危急情况（胸痛、呼吸困难、言语不清、一侧无力等）请立即拨打 120。

---

## 一、快速开始（本地运行）

**环境要求**：Python 3.10+（建议 3.12）。

### Windows（推荐）

1. 双击 `run.bat`（或右键用 PowerShell 运行 `run.ps1`）。
2. 首次运行会自动安装依赖（`starlette`、`uvicorn`、`pydantic`）。
3. 自动在浏览器打开 `http://127.0.0.1:8000`。

### 手动启动

```bash
pip install -r requirements.txt
python -m app.main
```

打开浏览器访问 <http://127.0.0.1:8000>。

---

## 二、功能与使用

### 登录与演示账号

打开后进入**登录页**（`/login`），首次使用会自动生成演示数据与账号（密码均为 `123456`）：

| 身份 | 账号 | 说明 |
|---|---|---|
| 使用者 | `zhang` | 张奶奶，AI 智能导诊 |
| 监护人 | `zhangson` | 张先生，可编辑每日日程 |
| 医生 | `lidoctor` | 李医生，可开具医嘱 |

三方账号通过 `bindings` 自动绑定到同一使用者；也可在「监护人/医生」端输入使用者 ID 进行绑定。

| 页面 | 路径 | 说明 |
|---|---|---|
| 登录 | `/login` | 登录 / 注册（使用者、监护人、医生） |
| AI 智能导诊 | `/user` | 语音/文字症状分诊、结构化追问、记录指标、同步手环、SOS |
| 监护人看板 | `/guardian` | 最新指标、告警、**日程增删改**、趋势图、周报 |
| 医生工作台 | `/doctor` | 患者档案、**开具医嘱**、报告、导出诊断凭据 |

### 本次升级要点

- **账号体系**：注册/登录（PBKDF2 加盐）、会话令牌、使用者/监护人/医生三方绑定、按角色鉴权。
- **结构化追问**：AI 追问以卡片呈现，点击问题才展开选项（含「其他」），点选项才会作为回答发送。
- **通俗化知识库**：每个病症增加「大白话解释 + 权威来源（指南名）」。
- **可穿戴同步**：`/api/devices/sync` 支持真实推送或模拟拉取（华为手环等）。
- **医嘱与日程**：医生开医嘱自动生成每日提醒；监护人可增/改/删日程。
- **AI 语音**：TTS 文本规范化，`120` 读作「幺二零」、血压 `120/80` 读作「一百二十比八十」、手机号逐位读；可选接入 OpenAI 兼容 TTS（`AI_VOICE_API_KEY`），未配置则回退浏览器语音。
- **商业化建议**：见 [docs/COMMERCIAL_FEATURES.md](docs/COMMERCIAL_FEATURES.md)。

---

## 三、项目结构

```
MedAgent/
├── app/                      # 后端（Python）
│   ├── main.py               # Starlette 应用 + 路由 + 静态服务（入口）
│   ├── config.py             # 配置、指标参考区间、LLM 配置
│   ├── database.py           # SQLite 存储与 schema
│   ├── triage.py             # 分诊规则引擎（红/黄/绿）
│   ├── advice.py             # 生活/饮食建议引擎
│   ├── reports.py            # 周报/月报生成与 FHIR 导出
│   ├── alerts.py             # 告警与通知中心
│   ├── reminders.py          # 医嘱/测量提醒 + 调度线程
│   ├── seed.py               # 演示数据
│   └── data/triage_rules.json # 医学分诊规则（可维护、版本化）
├── frontend/                 # 前端（原生 HTML/CSS/JS，无构建）
│   ├── index.html / user.html / guardian.html / doctor.html
│   ├── css/style.css
│   └── js/{api,charts,common,user,guardian,doctor}.js
├── data/                     # 运行时生成：medagent.db
├── BASELINE.md               # 项目基线文档
├── requirements.txt
└── run.bat / run.ps1         # 一键启动器
```

---

## 四、API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/seed` | 生成演示数据 |
| POST | `/api/chat` | 症状对话分诊 |
| POST | `/api/sos` | 一键紧急呼救 |
| POST | `/api/metrics` | 手动录入 / 设备同步指标 |
| GET | `/api/metrics` | 查询指标序列 |
| GET | `/api/alerts` | 告警列表 |
| POST | `/api/alerts/{id}/ack` | 确认告警 |
| GET | `/api/reminders` | 提醒与今日待办 |
| POST | `/api/reminders/{id}/take` | 记录执行 |
| GET | `/api/reports/weekly` · `/monthly` | 生成周/月报 |
| GET | `/api/reports/{type}/export` | 导出 FHIR/JSON |
| GET | `/api/guardian/dashboard` | 监护人仪表盘 |
| GET | `/api/doctor/overview` | 医生视图 |
| GET/POST | `/api/users` · `/api/users/{id}` | 使用者档案 |

完整接口列表见 `app/main.py`。

---

## 五、打包为可安装应用（可选）

`run.bat` 已提供「双击即用」的桌面体验。如需**单文件 .exe**（无需装 Python），可用 PyInstaller：

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --name MedAgent \
  --add-data "app;app" --add-data "frontend;frontend" \
  --collect-all uvicorn --collect-all starlette \
  --hidden-import app.main \
  launcher.py
```

- 打包产物位于 `dist/MedAgent.exe`，双击即启动并自动打开浏览器。
- 打包后数据（SQLite）写入 `%LOCALAPPDATA%\MedAgent`，资源在 exe 内部（只读），已由 `app/config.py` 自动处理。
- 若打包遇到路径或依赖问题，直接使用 `run.bat` 即可，功能完全一致。

---

## 六、技术说明与设计边界

- **存储**：SQLite（单文件、零部署）。baseline 中的 PostgreSQL+TimescaleDB 用于多机构部署时再平滑替换（表结构一致）。
- **分诊安全**：LLM 负责「理解与表达」，**规则引擎负责风险判定与动作**，避免幻觉直接触发告警。分诊规则见 `app/data/triage_rules.json`，应由医学专业人士审核与版本化。
- **通知渠道**：MVP 阶段站内告警为事实来源，短信/电话渠道为接入点（见 `app/alerts.py` 的 `_dispatch`），需接入第三方服务。
- **设备接入**：`/api/devices/sync` 为统一入口，华为 Health Kit 等通过该接口对接。
- **可选 LLM 增强**：设置环境变量 `DEEPSEEK_API_KEY` 可启用（预留，见 `app/config.py`）；不配置则纯规则、完全离线可用。

---

## 七、已知限制（MVP）

- 语音依赖浏览器 Web Speech API（Chrome/Edge 体验最佳，需联网）。
- 短信/电话通知为模拟，未接入真实运营商。
- 华为手环等真实设备数据以 `/api/devices/sync` 接口模拟接收。
- 分诊规则为通用健康教育的演示版本，正式使用前需医学专业人士审核。

---

## 八、无法运行时的排查

双击 `run.bat` 失败，按下面顺序自查（把报错信息发出来能更快定位）：

1. **是否装了 Python**：在命令行执行 `python --version`（或 `py -3 --version`）。没有则到 <https://www.python.org/downloads/> 安装，勾选 **Add python.exe to PATH**。
2. **依赖是否装成功**：手动执行 `python -m pip install -r requirements.txt`，看是否报网络错误。国内网络慢/失败时改用镜像：
   ```bash
   python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```
3. **报 `No module named 'starlette'`（最常见）**：说明依赖没装上。先执行第 2 步；仍不行就确认 `pip` 能联网。
4. **端口是否被占用**：启动报 `address already in use` 时，换个端口：
   ```bash
   $env:MEDAGENT_PORT=8001; python -m app.main
   ```
5. **最稳的启动方式**：命令行进入项目目录后直接运行 `python -m app.main`，再手动打开 <http://127.0.0.1:8000>。

> **历史问题（已修复）**：早期 `run.bat` 同时含 `chcp 65001` 与 UTF-8 中文，会让 cmd.exe 重读脚本时错行，导致 `pip install` 那行被吞掉、报 `No module named 'starlette'`。现已改为**纯 ASCII 启动脚本**。若你克隆的是旧版本，请先 `git pull`（或重新克隆）再运行。
