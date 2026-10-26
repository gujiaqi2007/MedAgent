# MedAgent · 运行说明

> 健康信息整理与就医导航助手。**不做诊断、不开药、不替代医生。**
> 本文是唯一的运行手册：装环境 → 配 Key → 启动 → 跑测试 → 演示 → 排错。

---

## 目录

1. [30 秒快速开始](#1-30-秒快速开始)
2. [环境要求](#2-环境要求)
3. [安装依赖](#3-安装依赖)
4. [配置模型（可选）](#4-配置模型可选)
5. [启动应用](#5-启动应用)
6. [运行测试](#6-运行测试)
7. [三个演示案例（照做即可复现）](#7-三个演示案例照做即可复现)
8. [目录结构与模块职责](#8-目录结构与模块职责)
9. [维护指南：加一条规则 / 一条知识](#9-维护指南加一条规则--一条知识)
10. [来源可信度说明](#10-来源可信度说明)
11. [常见问题排错](#11-常见问题排错)
12. [提交前自检清单](#12-提交前自检清单)

---

## 1. 30 秒快速开始

**不需要 API Key 也能完整跑通**（离线演示模式，界面上会有橙色横幅说明）。

```powershell
# Windows PowerShell
cd E:\MedAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

```bash
# macOS / Linux
cd MedAgent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

浏览器打开 <http://localhost:8501>，在底部输入框输入：

```text
咳嗽三天，有点痰，5 分，没有发烧
```

应当看到：灰色/蓝色风险卡 → 追问或直接出报告 → 「评估报告」区域里 8 个区块 + 可点击的知识来源链接。

> 如果 8501 被占用：`python -m streamlit run app.py --server.port 8502`

---

## 2. 环境要求

| 项 | 要求 | 说明 |
|---|---|---|
| Python | **3.10 – 3.12** | 已在 3.12.0 上验证；3.9 不支持 `X \| None` 写法 |
| 操作系统 | Windows / macOS / Linux | 无平台特定代码 |
| 浏览器 | Chrome / Edge 最新版 | 演示建议 1920×1080、浏览器缩放 110% |
| 网络 | 离线模式不需要；在线模式需要能访问模型服务 | 比赛现场建议先跑离线模式 |
| 依赖 | 见 `requirements.txt`（4 个包） | 不引入 LangChain、向量库、数据库 |

---

## 3. 安装依赖

### 3.1 推荐：虚拟环境（避免污染系统 Python）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # PowerShell
# 若提示"禁止运行脚本"：
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 安装

```bash
python -m pip install -U pip
python -m pip install -r requirements.txt
```

`requirements.txt` 内容：

```text
streamlit>=1.32,<2.0
openai>=1.30
python-dotenv>=1.0
pytest>=8.0
```

> `openai` 未安装也能启动（会自动进入离线模式），但建议装上，否则在线模式不可用。
> 若 pip 报依赖冲突（例如 numpy 版本），**不影响本项目**，本项目不依赖 numpy。

### 3.3 验证安装

```bash
python -c "import streamlit, openai, dotenv; print('ok')"
```

---

## 4. 配置模型（可选）

### 4.1 复制模板

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

### 4.2 填写三个必需项

```dotenv
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

要求：服务需兼容 **OpenAI Chat Completions 接口**，并支持 **Tool Calling**（本项目会真实执行工具调用循环）。

常见可选值：

| 服务 | LLM_BASE_URL | LLM_MODEL 示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里云百炼（兼容模式） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

> 只填 `LLM_API_KEY` 为空 → 离线模式；填了但填错 → 启动后调用时会**自动降级**并在界面提示，不会崩溃。

### 4.3 安全约定

* `.env` 已在 `.gitignore` 中，**不要提交**；
* 日志只打印 `sk-xxxx***` 形式的脱敏 Key；
* 界面上侧边栏显示的是脱敏 Key；
* 演示前请执行 `git status` 确认 `.env` 未被跟踪。

---

## 5. 启动应用

```bash
python -m streamlit run app.py
```

指定端口 / 局域网演示：

```bash
python -m streamlit run app.py --server.port 8502 --server.address 0.0.0.0
```

### 5.1 界面结构（从上到下）

| 区域 | 内容 |
|---|---|
| 顶部 | 标题 + 一句话定位 |
| 模式横幅 | 橙色＝离线演示模式；蓝色＝在线模式（含模型名） |
| 免责声明 | 可展开的折叠框（首屏可见） |
| 评估进度 | 4 个指标：主要症状 / 持续时间 / 严重程度 / 伴随症状 |
| 对话区 | 多轮消息，助手头像左侧 |
| 风险卡 | 🚨 红 / ⚠️ 橙 / ℹ️ 蓝 / ❓ 灰 四色，可展开「规则命中详情」 |
| 输入框 | 底部 `chat_input`，评估结束后自动禁用 |
| 评估报告 | 8 个区块 + 来源链接 |
| 侧边栏 | 重新开始、模式、模型、Key（脱敏）、规则数、知识条目数 |

### 5.2 交互规则（实现层面，演示时可直接讲）

* 一次只问 **1–2 个**缺失信息，最多追问 **3 轮**；已回答的槽位不会再问。
* 命中危险信号 → **立刻**出红色卡片，不追问、不检索、不等模型。
* 信息不足 3 轮后 → 出「信息不足」报告，明确写"无法充分评估"。
* "🔄 重新开始"会清空会话、槽位、风险结果、报告与追问计数。

---

## 6. 运行测试

```bash
python -m pytest -q
```

预期输出（当前实测）：

```text
74 passed in ~8s
```

分模块运行：

```bash
python -m pytest tests/test_rules.py -v          # 规则引擎
python -m pytest tests/test_retrieval.py -v      # 知识检索
python -m pytest tests/test_controller.py -v     # 控制流程 / 降级 / 报告校验
python -m pytest tests/test_offline.py -v        # 离线模式
python -m pytest tests/test_app_smoke.py -v      # Streamlit 页面冒烟（AppTest）
```

### 6.1 测试覆盖了什么

| 文件 | 覆盖点 | 对应用例 |
|---|---|---|
| `test_rules.py` | 12 条规则分级、否定、假设句、过去时、信息不足、纯函数、规则文件自检 | case_01–16 |
| `test_retrieval.py` | 返回内容+来源、空查询、无匹配、低分过滤、pending 排除、空知识库 | case_17 |
| `test_controller.py` | 紧急短路、追问上限、不重复追问、鉴权失败降级、工具超限降级、报告校验（改风险等级/删编造条目/改 URL） | case_18 + P8/P9 |
| `test_offline.py` | 报告 8 区块、离线标注、空知识库提示、追问问法轮换、紧急卡含 120 | P10 |
| `test_app_smoke.py` | 页面能启动、离线横幅可见、紧急/普通两轮能出报告 | P18 |

### 6.2 免责声明

测试结果来自**真实执行**，请勿手写通过率。提交文档时贴 `pytest -q` 的终端截图。

---

## 7. 三个演示案例（照做即可复现）

### 案例 A：普通症状多轮对话 → 常规报告

**输入**：`咳嗽三天，有点痰，5 分，没有发烧`

**预期**：蓝色「常规」卡 → 报告含 8 区块 → 知识来源出现《咳嗽的居家观察要点》，链接可点。

**讲解点**：`没有发烧` 被否定处理，不会触发发热规则；检索词只来自结构化槽位。

---

### 案例 B：紧急危险信号 → 立即红色卡

**输入**：`胸口压着疼，还一直出汗，大概二十分钟了`

**预期**：**不追问**，立刻出现红色「紧急」卡，含「立即拨打 120」；展开「规则命中详情」可见 `R001` 与依据原句。

**讲解点**：规则命中即短路，不等待模型与检索；模型无权修改风险等级。

---

### 案例 C：信息不足 → 追问 3 轮 → 明确"无法充分评估"

**输入**：`不舒服` → 再输入 `三天了，大概 5 分` → 再输入 `还是不舒服` → 再输入 `嗯`

**预期**：前 3 次追问（问法不重复），第 4 次输出灰色「信息不足」报告，明确列出缺失项。

**讲解点**：追问轮次由代码控制，不由模型决定。

---

### 附加案例：降级演示（评委常问）

1. 把 `.env` 里的 `LLM_API_KEY` 改成 `sk-invalid`；
2. 重启应用，输入 `咳嗽三天，有痰，5 分`；
3. 预期：界面提示"鉴权失败（请检查 LLM_API_KEY），已改用本地规则与模板生成报告"，报告仍然完整。

---

## 8. 目录结构与模块职责

```text
MedAgent/
├── app.py                  # Streamlit 前端（只做渲染与状态编排）
├── contracts.py            # ★ 全局数据契约：枚举 / dataclass / 常量（改动需通知全组）
├── agent/
│   ├── controller.py       # 状态机：槽位抽取 → 规则筛查 → 追问/报告 → 降级
│   ├── llm.py              # 配置、客户端、工具调用循环、报告 JSON 校验
│   ├── offline.py          # 离线模板：追问 / 报告 / 紧急卡
│   └── prompts.py          # 所有提示词集中管理
├── tools/
│   ├── triage_rules.py     # 确定性规则引擎（纯函数，禁止引入模型 SDK）
│   └── medical_search.py   # 关键词检索（纯函数，无外部服务）
├── knowledge/
│   ├── rules.json          # 12 条风险规则（改这里就能加规则）
│   └── medical_knowledge.json  # 14 条知识条目
├── tests/                  # pytest + 18 条合成用例
├── docs/
│   ├── architecture.md     # 架构、数据流、规则来源表
│   └── baseline.md         # 施工图纸（18 处修补）
├── .env.example / .gitignore / requirements.txt / README.md
```

依赖方向（只许单向）：

```text
app.py → agent/controller.py → tools/*.py
                 ├→ agent/llm.py
                 └→ agent/offline.py
所有模块 → contracts.py
```

**禁止**：`tools/*` 反向 import `agent/*`；`app.py` 里写业务判断；`controller.py` 里出现 `st.*`。

---

## 9. 维护指南：加一条规则 / 一条知识

### 9.1 加风险规则（不用改 Python）

编辑 `knowledge/rules.json`，在 `rules` 数组里追加：

```json
{
  "id": "R013",
  "level": "urgent",
  "category": "你的分类",
  "title": "一句话标题",
  "keywords": ["关键词1", "关键词2"],
  "negative_keywords": ["没有关键词1"],
  "context_hint": ["加分上下文词"],
  "min_hits": 1,
  "min_context": 1,
  "message": "面向用户的一句解释（不要写疾病名开头）",
  "action": ["可执行动作 1", "可执行动作 2"],
  "sources": ["S-ER-TRIAGE"],
  "applies_to": null,
  "notes": "适用范围与局限"
}
```

规则约束（加载时会自动校验，不合法直接报错）：

* `id` 唯一；`level ∈ {emergency, urgent, routine, insufficient}`
* `keywords`、`sources`、`message` 不能为空
* `min_context: 1` 表示"关键词 + 至少一个上下文词"才算命中（用于避免单字误报，例如 R011/R012）
* `applies_to`：`null` 表示不限人群，可选 `["infant","child","elderly","pregnant"]`

**加完必须补一条负例测试**（"我没有…"），否则很容易误报。

### 9.2 加知识条目（不用改 Python）

在 `knowledge/medical_knowledge.json` 的 `entries` 里追加：

```json
{
  "id": "k015",
  "title": "标题",
  "topics": ["主题词"],
  "keywords": ["关键词"],
  "summary": "一句话摘要",
  "content": "3–5 条行为建议，不含药物剂量",
  "org": "来源机构",
  "source_title": "页面标题",
  "source_url": "https://...",
  "source_type": "government|who|hospital|manual|pending",
  "link_level": "direct|site",
  "status": "verified|pending",
  "updated_at": "2026-10-26",
  "notes": "适用范围与局限"
}
```

**硬规则**：

* `source_url` 必须是你自己**点开过、能看到对应内容**的链接；
* 打不开 / 需要登录 / 只是站点首页 → `status: "pending"`，它不会进入报告引用区；
* 严禁编造论文标题、DOI、条款号。

### 9.3 改完必做的三件事

```bash
python -m pytest -q          # 1. 测试全绿
python -m streamlit run app.py   # 2. 页面能开、能出报告
git status                   # 3. .env 没被提交
```

---

## 10. 来源可信度说明

本项目的知识条目采用**两级链接诚实标注**，这与"不许编造来源"的要求配套：

| `link_level` | 含义 | 界面展示 |
|---|---|---|
| `direct` | 直达该主题的科普页面（已人工核对可打开） | 「直达页面」 |
| `site` | 机构**站点级**入口（首页/栏目），具体文章需站内检索 | 「站点入口」 |

| `status` | 含义 | 是否进入报告 |
|---|---|---|
| `verified` | 链接可打开，机构可信 | ✅ 是 |
| `pending` | 尚未人工核对 | ❌ 否（仅在内部检索可见） |

当前版本：**14 条条目**，其中 `verified` 13 条、`pending` 1 条（k008 腹痛，链接待核对）。
提交前请由知识库负责人把 `site` 换成具体文章直达链接，并把 `pending` 全部清零——这是评审最容易追问的点。

已核对的来源机构（2026-10-26 实测可访问）：

* 中国疾病预防控制中心 <https://www.chinacdc.cn/>
* 世界卫生组织中文站 <https://www.who.int/zh/>
* 默沙东诊疗手册（家庭版）中文站 <https://www.msdmanuals.cn/>
* 英国 NHS <https://www.nhs.uk/conditions/fever-in-children/>

> 国家卫生健康委官网存在反爬（返回 412），因此未作为条目来源；如要引用，请人工打开后截图存档。

---

## 11. 常见问题排错

| 现象 | 原因 | 解决 |
|---|---|---|
| `streamlit: 无法将"streamlit"项识别为 cmdlet` | 未激活虚拟环境 | `.\\.venv\\Scripts\\Activate.ps1`，然后 `python -m streamlit run app.py` |
| 页面能开但一输入就报错 | 规则 / 知识库 JSON 语法错误 | 侧边栏会显示「风险规则：⚠️ 加载失败」+ 原因；用 `python -m json.tool knowledge/rules.json` 校验 |
| 中文显示为乱码或 `\uXXXX` | 文件被非 UTF-8 保存 | 所有 JSON 必须 UTF-8 无 BOM 保存；代码里 `json.dump(..., ensure_ascii=False)` |
| 每次点击都调用一次模型（费用异常） | 把模型调用写在了渲染路径 | 本项目只在 `chat_input` 提交分支调用；自定义代码时保持这条纪律 |
| 提示"鉴权失败" | Key 错误 / Base URL 不匹配 | 检查 `.env`；先确认服务支持 OpenAI 兼容接口 |
| 提示"模型响应超时" | 网络或服务慢 | 已自动降级为本地模板；可把 `LLM_TIMEOUT` 调到 40 |
| 模型一直调用工具 | 模型行为 | 已硬限制 `MAX_TOOL_ROUNDS=3`，超出即降级 |
| 端口 8501 被占用 | 上一个进程没退 | `--server.port 8502`，或 `Get-Process python \| Stop-Process` |
| `AppTest` 测试很慢 | 每个用例都要跑一遍脚本 | 属正常现象，约 1–3 秒/用例 |
| 报告里知识条目为空 | 该主题无匹配条目（正常） | 界面会提示"本次未检索到可靠知识条目"，这是刻意设计，不要硬凑 |

---

## 12. 提交前自检清单

```bash
python -m pytest -q                # 全绿
python -m streamlit run app.py     # 页面正常
git status                         # .env / __pycache__ / logs 未入仓
python -m json.tool knowledge/rules.json > $null
python -m json.tool knowledge/medical_knowledge.json > $null
```

- [ ] 未配置 Key 时能启动并显著标注「离线演示模式」
- [ ] 配置 Key 后能多轮对话并生成报告（日志可见 `llm call ...`）
- [ ] 三个演示案例均可复现（案例 A/B/C）
- [ ] 危险信号 1 次交互内出红色卡，无追问
- [ ] 报告 8 区块齐全，来源链接可点
- [ ] "重新开始"彻底清空
- [ ] 全文无"确诊 / 准确率 / 临床验证"表述
- [ ] 无药物剂量建议
- [ ] `.env` 未被提交

---

## 附：与设计文档的对应关系

| 本文小节 | 设计文档位置 |
|---|---|
| 风险分级 / 规则字段 | `docs/architecture.md` 与 `BASELINE.md` §6 |
| 知识条目与检索打分 | `BASELINE.md` §7 |
| 追问槽位与上限 | `BASELINE.md` §8 |
| 工具调用循环 / 熔断参数 | `BASELINE.md` §9 |
| 报告 8 区块与三色卡 | `BASELINE.md` §11 |
| 十天计划与分工 | `BASELINE.md` §12 |

**版本**：MedAgent v1.0 ｜ 规则 v1.0（12 条）｜ 知识库 v1.0（14 条）｜ 2026-10-26
