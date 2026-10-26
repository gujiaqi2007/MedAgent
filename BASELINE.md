# MedAgent Baseline v1.0

> **这份文件是什么**：MedAgent 的「施工图纸」。它把原始需求整理成一份**按顺序照做即可**的执行规格，同时修掉了原方案里会导致返工、演示翻车或安全表述风险的 18 处问题（见 §2）。
>
> **适用对象**：四名队员 + 指导老师。任何一人读完 §4–§7 就应该能独立开工，不需要再问"接口长什么样"。
>
> **使用方式**：D1 全员一起读 §1–§3 并确认；然后每人按 §12 认领自己的文件；§16 是提测和验收的唯一标准。
>
> **基线冻结规则**：§5 的数据契约一旦冻结（建议 D1 晚上），任何人改动必须群里说明并在 commit message 里标注 `contract:`。这是四人并行不打架的前提。

---

## 目录

- [1. 项目定义与非目标](#1-项目定义与非目标)
- [2. 修补清单（相对原需求 / GPT 方案的 18 处改动）](#2-修补清单相对原需求--gpt-方案的-18-处改动)
- [3. 用词与合规红线](#3-用词与合规红线)
- [4. 目录结构与文件职责](#4-目录结构与文件职责)
- [5. 数据契约（先冻结，再开发）](#5-数据契约先冻结再开发)
- [6. 风险规则引擎规格](#6-风险规则引擎规格)
- [7. 知识库与检索规格](#7-知识库与检索规格)
- [8. 对话状态与追问槽位](#8-对话状态与追问槽位)
- [9. Agent 控制流程](#9-agent-控制流程)
- [10. LLM 层与离线模式](#10-llm-层与离线模式)
- [11. 报告与前端规格](#11-报告与前端规格)
- [12. 十天执行计划（含分工）](#12-十天执行计划含分工)
- [13. 测试规格](#13-测试规格)
- [14. Demo 视频脚本](#14-demo-视频脚本)
- [15. 提交物清单](#15-提交物清单)
- [16. 验收清单（DoD）](#16-验收清单dod)
- [17. 常见坑](#17-常见坑)
- [附录 A 固定文案](#附录-a-固定文案)
- [附录 B 规则来源与待核实标注](#附录-b-规则来源与待核实标注)
- [附录 C 合成案例模板](#附录-c-合成案例模板)

---

## 1. 项目定义与非目标

### 1.1 一句话定义

MedAgent 是一个**中文症状信息整理与就医导航助手**：通过多轮对话补齐关键信息 → 用**独立的确定性规则引擎**做风险分层 → 从**可溯源的本地知识库**检索条目 → 由大模型整合成一份**分层标注来源**的结构化报告。

### 1.2 目标用户与使用场景

| 项 | 内容 |
|---|---|
| 用户 | 有不适症状、不知道"要不要去医院/挂哪个科"的普通成年人（及其家属代述） |
| 场景 | 家庭场景下的初步信息整理，5 分钟内拿到一份"我该做什么"的清单 |
| 交付物 | 结构化报告（症状摘要 / 已收集信息 / 缺失信息 / 风险分层 / 下一步行动 / 知识摘要 / 来源 / 免责声明） |

### 1.3 非目标（写进 README，答辩时主动说）

1. **不做诊断**：不输出"你患有 X 病"，只输出"存在需要尽快就医评估的危险信号"或"目前未见规则覆盖的紧急信号"。
2. **不开药**：不出现具体药名 + 剂量 + 疗程的组合建议（可以出现"是否需要退热药请咨询医师/药师"这类指向性表述）。
3. **不做个体化治疗决策**：不判断"要不要手术/要不要住院"。
4. **不替代医生**：所有报告页脚固定免责声明（附录 A）。
5. **不做真实患者数据**：全部演示数据为合成案例。
6. **不宣称准确率**：不写"准确率 92%"这类没有对照研究支撑的数字；如需量化，只报"规则单测通过数 / 用例数"。

### 1.4 成功判据（比赛层面）

- 未配置 API Key 时，`streamlit run app.py` 能直接跑通全流程并显著标注「离线演示模式」。
- 配置 API Key 后，多轮对话 + 工具调用 + 报告生成闭环可用。
- 危险信号案例：从输入到红色紧急提示 ≤ 1 次交互，不被追问或检索延迟。
- `pytest -q` 全绿，且能贴出真实输出。
- 新同学照 README 30 分钟内跑起来。

---

## 2. 修补清单（相对原需求 / GPT 方案的 18 处改动）

> 这一节是本文档的核心价值。左列是原方案的说法，中列是问题，右列是修补后的做法。后文用【P7】这样的标记回指。

| # | 原方案的做法 | 风险 / 问题 | 修补后的做法 | 落地位置 |
|---|---|---|---|---|
| **P1** | 由 LLM 判断"是否需要追问" | 模型时好时坏、同一输入两次结果不同、追问轮次不可控，演示会翻车 | **是否追问由确定性槽位引擎判定**（§8），LLM 只负责把追问"说得自然"；决策不可交给模型 | §8、§9 |
| **P2** | 风险只分"命中危险信号 / 未命中" | 未命中被用户读成"安全"，等于给出隐性阴性结论 | 改为四态：`EMERGENCY / URGENT / ROUTINE / INSUFFICIENT`；**默认不是低风险**，信息不足时只能是 `INSUFFICIENT` | §6.2 |
| **P3** | "信息不足时标记无法充分评估"只写在原则里 | 没有可执行判据，实现时容易退化成永远 ROUTINE | 定义 `required_slots`（主诉 + 时长 + 严重度 + 至少 1 个伴随/背景），缺一即 `INSUFFICIENT`，并列出缺哪几项 | §6.5、§8 |
| **P4** | 关键词匹配直接命中 | "我没有胸痛"、"如果胸痛怎么办"会被判成紧急，误报毁演示 | 增加**否定窗口 + 疑问/假设句降权**（§6.4），并为核心规则配 `negative_keywords` | §6.4 |
| **P5** | 无人群修饰 | 儿童/孕产/高龄/免疫抑制人群阈值应更保守，否则出现"3 个月婴儿发热判为 ROUTINE" | 独立 `modifiers` 层：只做**升级与补问**，不做诊断（§6.6） | §6.6 |
| **P6** | 知识检索"返回 top-k" | 无相关条目时也会硬凑 3 条，等于编造依据 | 加**最低相关分阈值**；低于阈值返回空，并明确输出"本次未检索到可靠条目"（§7.5） | §7.5 |
| **P7** | 知识条目"尽可能包含来源链接" | 最容易出现假链接、假文献，是比赛硬伤 | 域名白名单 + 加载时校验 `source_url`；无来源的条目 `status=pending` 且**不得进入报告引用区**（§7.3） | §7.3 |
| **P8** | "设置合理的调用次数上限" | 没给数字，等于没做 | 硬编码 `MAX_TOOL_ROUNDS=3`、`LLM_TIMEOUT=25s`、总流程 `40s` 熔断；超限走降级模板 | §9.3 |
| **P9** | 让模型输出"结构化报告" | 自由文本解析必崩，模型加一句"以下是报告"就解析失败 | 强制 **JSON 输出 + Pydantic/手写 schema 校验 + 一次自动修复重试**，再失败降级 | §10.4 |
| **P10** | 离线模式"可演示" | 容易做得像真模型，评委一问就露；也容易让队员以为自己接通了 | 顶部固定橙色横幅「离线演示模式（规则模板，非模型生成）」；报告每个区块标注生成方式 | §10.5、§11.2 |
| **P11** | 无上下文/状态管理细节 | Streamlit 每次交互重跑脚本，状态丢失、重复调用 API | 规定 `st.session_state` 的完整键表与写入时机；**渲染路径禁止调用 LLM**，只在按钮回调里调用（§11.3） | §11.3 |
| **P12** | "报告要区分三类信息"只是要求 | 实现时混在一段话里，等于没区分 | 报告用**三段式 + 标签**：`[用户提供]` / `[规则筛查]` / `[模型解释]`，每条结论带标签 | §11.2 |
| **P13** | 测试"至少编写以下" | 没给用例，最后只写 3 个 happy path | 给出 18 条**可复制进 `tests/cases.json`** 的用例表（§13.2），含负例和降级用例 | §13.2 |
| **P14** | 两周计划按"阶段"划分 | 阶段目标模糊，容易第 8 天还在改架构 | 改为 **D1–D10 天级任务 + 每日完成判据 + 4 人分工**，D3 必须有一次能录屏的闭环（§12） | §12 |
| **P15** | 四人分工只写"负责 XX" | 接口不明导致互相等待 | 分工绑定到**文件**和**契约**，并规定 D1 先合并 `contracts.py`（§4.3、§5） | §4.3 |
| **P16** | 追问"根据已有信息判断" | 不问性别年龄，导致孕产/儿童场景无法评估 | 槽位表固定 6 类必问 + 4 类条件问；每类给中文追问模板（§8.2） | §8.2 |
| **P17** | 未定义日志与隐私 | 调试时把 API Key、症状原文打进日志/截图 | 日志脱敏规则：不打印 key、不打印完整输入（只打长度+哈希前 6 位）、`.env` 进 `.gitignore` | §17 |
| **P18** | 未定义"知识库为空/模型失败"的界面 | 白屏报错，演示事故 | 三类异常的三套固定提示文案 + 永远可用的"仅规则模式"（§11.4、附录 A） | §11.4 |

**另外 4 条一句话级修补**（不单列）：

- 数字统一：报告里出现的所有阈值（体温、时长）必须来自规则文件，**不允许模型自由发挥数字**。
- 规则命中即**短路**：EMERGENCY 时不等检索、不追问，直接出紧急卡（原方案有写，但实现时常被"先检索再判断"覆盖）。
- "不做临床验证"的表述要主动写进文档，不要等人问。
- 报告里的知识摘要必须**可点击回原文**，不能只有文字。

---

## 3. 用词与合规红线

### 3.1 允许 / 禁止用词表

| 场景 | ✅ 用 | ❌ 不要用 |
|---|---|---|
| 风险结论 | "存在需要**尽快就医**评估的危险信号"、"建议**今日内**就诊"、"建议**立即**拨打 120" | "你患有…"、"确诊为…"、"大概率是…"、"排除…" |
| 可能性 | "可能与…相关，需医生判断" | "很可能是肺炎"、"基本可以确定" |
| 用药 | "是否需要用退热药，请咨询医师或药师" | "口服布洛芬 0.3g 每日三次" |
| 证据 | "来源：××（链接）"、"知识库暂无对应条目" | 编造论文名、期刊、DOI、页码 |
| 能力 | "本工具用于健康信息整理与就医导航" | "临床验证"、"诊断准确率 9x%" |

### 3.2 三条硬性技术红线

1. 规则引擎**不得**调用 LLM。`tools/triage_rules.py` 里出现 `openai` 这个词即为违规（可在测试里断言）。
2. 报告生成**不得**绕过规则结果：模型输出的 `risk.level` 与规则结果冲突时，**以规则为准**并在报告中说明"模型判断与规则不一致，已采用规则结论"。
3. 知识库**不得**出现无法访问的 URL 或"看起来像论文"的条目。`status=pending` 的条目只做内部参考，不进报告。

---

## 4. 目录结构与文件职责

### 4.1 最终目录

```text
MedAgent/
├── app.py                      # Streamlit 入口（只做 UI 与状态编排，≤300 行）
├── contracts.py                # ★ D1 冻结：所有 dataclass / 枚举 / 常量（P15）
├── agent/
│   ├── __init__.py
│   ├── controller.py           # 状态机 + 工具调用循环 + 降级
│   ├── llm.py                  # 客户端封装、超时、重试、JSON 校验
│   ├── offline.py              # 离线模板引擎（P10）
│   └── prompts.py              # 所有 prompt 常量，禁止散落在业务代码里
├── tools/
│   ├── __init__.py
│   ├── triage_rules.py         # 规则引擎（纯函数，无网络）
│   └── medical_search.py       # 关键词检索（纯函数，无网络）
├── knowledge/
│   ├── medical_knowledge.json  # 正式条目
│   ├── rules.json              # 风险规则（与代码分离，便于非程序员添加）
│   └── sources/                # 每条来源的截图/存档说明（可选，加分）
├── tests/
│   ├── test_rules.py
│   ├── test_retrieval.py
│   ├── test_controller.py
│   ├── test_offline.py
│   └── cases.json              # 18 条合成用例（§13.2）
├── docs/
│   ├── baseline.md             # ← 本文件（提交时放这里）
│   ├── architecture.md
│   ├── project_description.md
│   └── demo_script.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

### 4.2 模块依赖方向（只许单向）

```text
app.py  ──►  agent/controller.py  ──►  tools/triage_rules.py
                    │                └►  tools/medical_search.py
                    ├──►  agent/llm.py
                    └──►  agent/offline.py
所有模块 ──►  contracts.py（只依赖它，不互相 import）
```

**禁止**：`tools/*` 反向 import `agent/*`；`app.py` 里写业务判断；`controller.py` 里写 `st.*`。

### 4.3 四人分工（按文件绑定）

| 角色 | 负责文件 | 关键交付 | 不能碰 |
|---|---|---|---|
| A · 集成/模型 | `contracts.py`、`agent/*`、`app.py` | 状态机、工具循环、降级、UI 编排 | `knowledge/*.json` 内容 |
| B · 医学知识 | `knowledge/*.json`、`tools/medical_search.py`、`docs/architecture.md` 的知识部分 | 规则表 + 知识库 + 检索 | `agent/*` |
| C · 前端/测试 | `app.py` 的展示层、`tests/*` | 界面分区、测试用例、`pytest` 全绿 | 规则内容（可提 issue） |
| D · 产品/文档 | `docs/*`、`tests/cases.json`、演示视频 | 说明文档、案例、脚本、视频 | 代码 |

**协作约定**：D1 晚上 A 提交 `contracts.py` + 一页接口说明；之后 B/C 可以完全并行。任何人需要新增字段，先在群里发"契约变更"，A 合并后再动。C 的测试**只依赖 contracts**，所以可以在功能没写完时先写测试（红灯开发）。

---

## 5. 数据契约（先冻结，再开发）

> 全部放在 `contracts.py`，用 `dataclasses` + `enum`，**不用 pydantic**（少一个依赖，且 Streamlit Cloud 上更稳）。

### 5.1 枚举

```python
class RiskLevel(str, Enum):
    EMERGENCY = "emergency"      # 立即急诊/拨打 120
    URGENT    = "urgent"         # 24 小时内就医
    ROUTINE   = "routine"        # 可择期/居家观察，给出观察要点
    INSUFFICIENT = "insufficient" # 信息不足，无法充分评估（默认态）
```

```python
class SourceTag(str, Enum):
    USER  = "user"        # 用户提供
    RULE  = "rule"        # 规则引擎
    MODEL = "model"       # 模型解释
    KB    = "kb"          # 知识库条目
```

### 5.2 `Slots`（已收集的结构化信息）

```python
@dataclass
class Slots:
    chief_complaint: str | None = None      # 主诉，用户原话摘要
    duration: str | None = None             # 时长（保留原话，如"三天"）
    severity: int | None = None             # 0-10 自评；无法量化时 None
    associated: list[str] = field(default_factory=list)   # 伴随症状
    age_group: str | None = None            # "infant"|"child"|"adult"|"elderly"|None
    sex: str | None = None                  # "female"|"male"|"unspecified"|None
    pregnant: bool | None = None            # 仅 sex=female 时询问
    chronic: list[str] = field(default_factory=list)      # 基础病
    immunocompromised: bool | None = None
    negations: list[str] = field(default_factory=list)    # "无胸痛" 抽出的项（P4）
```

**规则**：槽位只从**用户明说的内容**填充，模型不得推断"应该是中年男性"。

### 5.3 `TriageResult`

```python
@dataclass
class TriageResult:
    level: RiskLevel
    matched_rules: list[str]         # rule id
    reasons: list[str]               # 人话解释，逐条对应 rule.message
    missing_slots: list[str]         # 缺哪些（P3）
    modifiers_applied: list[str]     # P5
    red_flag_actions: list[str]      # 紧急时的行动清单（"立即拨打 120"）
    sources: list[str]               # 规则依据来源名（附录 B）
    screening_note: str              # 固定一句"规则筛查不等于诊断"
```

### 5.4 `KnowledgeHit`

```python
@dataclass
class KnowledgeHit:
    id: str
    title: str
    summary: str
    url: str
    org: str
    score: float
    matched_terms: list[str]
```

### 5.5 `Turn` 与 `Session`

```python
@dataclass
class Turn:
    role: str            # "user" | "assistant" | "system"
    content: str
    tag: SourceTag | None = None
    tool_calls: list[dict] = field(default_factory=list)

@dataclass
class Session:
    turns: list[Turn]
    slots: Slots
    triage: TriageResult | None
    hits: list[KnowledgeHit]
    report: dict | None          # 已通过 schema 校验的报告
    mode: str                    # "offline" | "online"
    ask_count: int               # 已追问轮次（P1，上限 3）
    finished: bool
```

### 5.6 报告 schema（模型必须输出的形状）

```json
{
  "chief_complaint": "string",
  "collected": {"duration": "string", "severity": "string", "associated": ["string"], "background": ["string"]},
  "missing": ["string"],
  "risk": {"level": "emergency|urgent|routine|insufficient", "basis": ["string"]},
  "next_steps": ["string"],
  "knowledge_summary": [{"id": "k001", "title": "string", "url": "string", "one_line": "string"}],
  "red_flags_to_watch": ["string"],
  "limitations": ["string"]
}
```

**校验规则**（`agent/llm.py` 内实现）：
1. 必填键齐全、类型正确、`risk.level` 在枚举内；
2. `risk.level` 必须与 `TriageResult.level` 一致，不一致则覆盖为规则值并追加一条 `limitations`；
3. `knowledge_summary[].id` 必须存在于本次 `hits` 中，**不存在的直接删除**（防止模型编造条目）；
4. 任一 `url` 必须等于知识库里的原值（防篡改）；
5. 校验失败 → 带着错误信息重试 1 次 → 仍失败 → 降级到离线模板（§10.5）。

---

## 6. 风险规则引擎规格

### 6.1 设计原则

1. **纯函数、无网络、可单测**：`screen(text: str, slots: Slots) -> TriageResult`。
2. **规则数据化**：规则写在 `knowledge/rules.json`，代码只做匹配与排序。B 可以不改 Python 就加规则。
3. **保守优先**：拿不准时升级而不是降级；但**不允许**为了保险把所有输入都判 EMERGENCY。
4. **可解释**：每次命中必须给出 `rule.message` 与来源。

### 6.2 分层与优先级（P2）

| 级别 | 含义 | 触发条件 | UI |
|---|---|---|---|
| `EMERGENCY` | 立即急诊 / 拨打 120 | 命中任一 `level=emergency` 规则且未是否定表述 | 红色卡片，置顶，**不再追问**，检索可选（仅作补充） |
| `URGENT` | 24h 内就医 | 命中 `level=urgent` 规则，或 severe 症状持续 | 橙色卡片 |
| `ROUTINE` | 可居家观察 / 择期就诊 | 槽位齐备且未命中上两级 | 蓝色卡片 + 观察要点 |
| `INSUFFICIENT` | 无法充分评估 | 无上两级命中，但 `required_slots` 缺项 | 灰色卡片 + 继续追问 |

**判定顺序**：`EMERGENCY → URGENT → (slots 完整性检查) → ROUTINE / INSUFFICIENT`。**永远不要**先判断"没命中就低风险"。

### 6.3 规则字段

```json
{
  "id": "R001",
  "level": "emergency",
  "category": "cardiopulmonary",
  "title": "持续胸痛",
  "keywords": ["胸痛", "胸口痛", "胸闷压榨", "胸口压着"],
  "negative_keywords": ["没有胸痛", "无胸痛", "不胸痛"],
  "context_hint": ["持续", "超过", "分钟", "出汗", "放射", "左臂", "濒死"],
  "min_hits": 1,
  "message": "描述中出现持续胸痛，可能与心脏急症相关，需要立即评估。",
  "action": ["立即拨打 120 或前往最近医院急诊", "不要自行驾车", "保持安静，等待救援"],
  "sources": ["S-ER-TRIAGE"],
  "applies_to": ["adult", "elderly"],
  "notes": "不用于确诊，仅触发就医建议"
}
```

字段说明：`context_hint` 是**加分项**不是必需项（有则提分，避免"胸痛"单字就爆红）；`applies_to` 为 `null` 表示不限人群；`sources` 指向附录 B 的编号。

### 6.4 否定与疑问处理（P4）

在匹配前先做一遍**预处理**：

1. **否定窗口**：关键词前 6 个字符内出现 `没有 / 无 / 不 / 未 / 否认 / 从来没 / 并没有` → 该命中作废，并写入 `slots.negations`。
2. **疑问/假设降权**：整句含 `如果 / 假如 / 会不会 / 是不是 / 要不要 / 请问` 且不含第一人称症状陈述 → 该句只做知识检索，不做紧急升级（但仍保留 URGENT 的可能）。
3. **家属代述**：`我爸 / 我妈 / 孩子 / 家人` 出现时**正常升级**（不要因为不是本人而忽略）。
4. **过去时**：`以前 / 去年 / 曾经` 且无 `现在 / 目前 / 今天` → 降一级，并在报告中注明"既往史"。

> 实现建议：一个 `_split_sentences(text)` + 逐句匹配，命中的 `sentence` 一起写进 `reasons`，方便演示时展示"为什么命中"。

### 6.5 信息不足的判据（P3）

```python
REQUIRED_SLOTS = ("chief_complaint", "duration", "severity")
SOFT_SLOTS     = ("associated", "age_group")   # 至少 1 个
```

- 缺任一 `REQUIRED_SLOTS`，或 `SOFT_SLOTS` 全空 → `INSUFFICIENT`；
- `missing_slots` 按 §8.2 的优先级排序输出，前端直接拿去生成追问。

### 6.6 人群修饰（P5）

修饰只做两件事：**升级**和**补问**，绝不诊断。

| 修饰 | 效果 |
|---|---|
| `age_group=infant`（<1 岁） | 发热相关规则升一级；`ROUTINE` 至少变 `URGENT` |
| `age_group=elderly`（≥65） | 同类症状升一级 |
| `pregnant=True` | 腹痛/出血/发热升一级，并追加"产科评估"行动 |
| `immunocompromised=True` | 发热升一级，追加"避免自行用退热药掩盖病情"提示 |
| `chronic` 含糖尿病/心肺疾病/肾病 | 相关症状升一级 |

实现为 `apply_modifiers(triage, slots) -> TriageResult`，`modifiers_applied` 记录生效项，报告里显式展示（"因年龄 <1 岁，风险等级上调"）。

### 6.7 必须实现的 12 条规则（最小集）

> 这些是**演示与测试都要覆盖**的规则。每条都要在附录 B 里能指到一个来源编号；无法核实的先标 `pending`，**不得**写成"依据《××指南》第 3.2 条"这种具体到条款的伪引用。

| id | 级别 | 触发要点 | 行动 |
|---|---|---|---|
| R001 | emergency | 持续胸痛/压榨感（尤其伴出汗、放射） | 拨打 120 |
| R002 | emergency | 单侧肢体无力/口角歪斜/言语不清（中风 120 识别） | 立即 120，记录发作时间 |
| R003 | emergency | 呼吸困难/不能平卧/口唇发紫 | 120 |
| R004 | emergency | 意识改变、抽搐、晕厥清醒后仍异常 | 120 |
| R005 | emergency | 大量出血（止不住/呕血/黑便伴头晕） | 120 |
| R006 | emergency | 剧烈腹痛且拒按/板状腹/持续加重 | 急诊 |
| R007 | emergency | 自杀/自伤意念或计划 | 危机干预热线 + 立即陪同就医 |
| R008 | emergency | 严重过敏：喉头发紧、面唇肿、全身风团伴呼吸不适 | 120（如有肾上腺素笔按医嘱使用） |
| R009 | urgent | 发热 ≥ 39℃ 或发热 >3 天不退 | 24h 内就诊 |
| R010 | urgent | 婴幼儿（<1 岁）发热 | 当日就诊 |
| R011 | urgent | 孕期腹痛/阴道出血/胎动减少 | 当日产科就诊 |
| R012 | urgent | 持续呕吐腹泻伴尿量明显减少、口干、站立头晕（脱水） | 24h 内就诊 |

> **不要**写"疑似心肌梗死""疑似脑梗"这种半诊断表述，统一写"可能与心脏/脑血管急症相关，需要立即评估"。

### 6.8 加载期自检

`load_rules()` 时断言：id 唯一、level 合法、`keywords` 非空、`sources` 非空、`message` 不以疾病名开头。失败则 `raise` 并在启动页显示"规则文件校验失败"，**不要静默跳过**。

---

## 7. 知识库与检索规格

### 7.1 条目 schema

```json
{
  "id": "k001",
  "title": "发热的家庭观察要点",
  "topics": ["fever"],
  "keywords": ["发热", "发烧", "体温", "退热"],
  "summary": "一句话摘要，≤60 字",
  "content": "3-5 句要点，全部是行为建议，不含药物剂量",
  "org": "来源机构名",
  "source_title": "页面/文件标题",
  "source_url": "https://...",
  "source_type": "government|who|hospital|manual|pending",
  "status": "verified|pending",
  "updated_at": "2026-10-26",
  "notes": "适用范围与局限"
}
```

### 7.2 规模与选题

- 目标 **12–20 条**，宁少勿假。建议覆盖：发热、咳嗽、腹泻/呕吐、头痛、腹痛、胸痛（就医指引）、皮疹、腰痛、头晕、孕期不适、儿童发热、老年人跌倒后、用药安全（"不要自行叠加感冒药"）、何时该去急诊。
- 每条 `content` 必须是**可执行的行为建议**，不是疾病科普长文。

### 7.3 来源白名单（P7）

只允许以下类型（示例，实际以能打开为准）：

- 国家级卫生机构官网（如国家卫生健康委、中国疾控中心官网首页/科普栏目）；
- 国际组织（WHO 官网）；
- 大型公立医院官方科普栏目；
- 公开出版、可在线查证的诊疗手册类站点。

**硬规则**：
1. `source_url` 必须你自己点开过、能看到对应内容；
2. 打不开/需登录 → `status=pending`，`source_type=pending`；
3. `pending` 条目**不进报告引用区**，只在内部检索时可见（报告里写"该主题暂无可引用来源"）；
4. 严禁出现具体论文标题 + DOI + 年份的三件套，除非你能打开原文。

### 7.4 检索实现（先关键词，后可选向量）

```python
def search(query: str, slots: Slots, top_k: int = 3, min_score: float = 0.30) -> list[KnowledgeHit]:
```

打分（全部小写、去空白后匹配）：

| 命中位置 | 分值 |
|---|---|
| 标题命中关键词 | +1.0 |
| `keywords` 命中 | +0.8 |
| `topics` 与主诉主题一致 | +0.6 |
| `summary/content` 命中 | +0.3 |
| 多个词命中 | 累加后 `× 0.5` 归一化到 0–1 |

- 结果按分排序，**过滤 `score < min_score`**；`status=pending` 只在不传 `include_pending=True` 时排除。
- 检索词来自：用户原话分词（按 `keywords` 表做子串匹配即可，不引入 jieba 也行；要引也可以，但要写进 requirements）。

### 7.5 空结果处理（P6）

返回空列表时：
- 报告 `knowledge_summary` 为空数组；
- 前端显示"本次未检索到可靠条目，以下建议仅基于规则筛查"；
- **不要**让模型"凭常识补一条"，prompt 里明确禁止。

### 7.6 可选扩展（最后做，做不完不影响）

向量检索放在 `tools/medical_search.py::search_vector()`，用 `sentence-transformers` 或调用 embedding API，**默认关闭**，通过 `ENABLE_VECTOR=1` 打开。文档里说明"关键词检索已满足 MVP，向量检索为可选实验"。

---

## 8. 对话状态与追问槽位

### 8.1 决策规则（P1）

```python
def next_action(session: Session) -> str:
    if session.triage and session.triage.level == RiskLevel.EMERGENCY:
        return "emergency_card"          # 立即出卡，不追问
    if missing_slots(session.slots) and session.ask_count < 3:
        return "ask"                     # 追问（由槽位决定问什么）
    return "report"                      # 信息够或轮次到上限，出报告
```

- `ask_count` 上限 **3**；到达上限仍缺信息 → 出 `INSUFFICIENT` 报告，明确写"因信息不足，无法充分评估"。
- 已填槽位**不再问**（`missing_slots` 只返回空项），这是原方案"避免重复询问"的可执行版本。

### 8.2 槽位与追问模板（P16）

按优先级问，一次只问 **1–2 个**（不要一次抛五个问题）：

| 优先级 | 槽位 | 追问模板 | 何时问 |
|---|---|---|---|
| 1 | `chief_complaint` | "你最不舒服的是哪里？大概是什么样的感觉？" | 首次输入为空或过于笼统 |
| 2 | `duration` | "这种情况大概持续多久了？是突然出现还是逐渐加重？" | 必问 |
| 3 | `severity` | "如果用 0–10 分给自己打分会是几分？现在还能正常活动吗？" | 必问 |
| 4 | `associated` | "除了这个，还有没有发热、呕吐、呼吸困难或皮疹之类的情况？" | 必问 |
| 5 | `age_group` | "方便说一下年龄吗？是成人、儿童还是老人？" | 影响修饰时必须问 |
| 6 | `sex` + `pregnant` | "是女性吗？是否怀孕或可能在孕期？" | 腹痛/出血/发热时必问 |
| 7 | `chronic` | "有没有高血压、糖尿病、心脏病等基础病？" | 老年或症状相关时问 |
| 8 | `immunocompromised` | "近期有没有化疗、长期用激素或免疫抑制剂？" | 反复发热时问 |

**追问的三种说法**（同一个槽位准备 3 个变体，避免复读机）：直接问、给选项问、说明原因问（"这个问题会影响风险判断，所以想确认一下"）。

### 8.3 状态更新

- 用户每轮输入 → `extract_slots(text) -> Slots`（先用规则，再让 LLM 补充，**LLM 结果只做 merge，不覆盖已有非空值**）。
- 任何槽位更新后立刻重跑 `screen()`，**不要**只在最后一轮跑（否则危险信号会被延迟到第 4 轮才提示）。
- 会话内 `turns` 保留完整历史，但送进模型的上下文只带**最近 6 轮 + 结构化 Slots 摘要**（控 token、控成本）。

---

## 9. Agent 控制流程

### 9.1 主流程（一次用户输入）

```text
1. 追加 Turn(user)
2. slots = merge(slots, extract_slots(text))        # 规则优先
3. triage = screen(text, slots)                     # 纯函数，<5ms
4. if triage.level == EMERGENCY:
       → 立即渲染紧急卡（含 action 列表 + 120）
       → 记录日志，返回（不进入 LLM 循环）
5. action = next_action(session)
6. if action == "ask":
       → 生成追问（离线：模板；在线：LLM 润色，失败回退模板）
       → ask_count += 1，返回
7. hits = search(query=主诉+关键词, slots)
8. if 在线模式:
       → llm.chat(tools=[screen_risk, search_knowledge], max_rounds=3)
       → 校验 JSON（§5.6）
   else:
       → offline.build_report(slots, triage, hits)
9. 渲染报告；finished=True
```

### 9.2 工具定义（必须真实执行，P8）

```python
TOOLS = [
  {"type": "function", "function": {
     "name": "screen_risk",
     "description": "对当前症状文本运行确定性风险筛查，返回风险等级与命中的规则。只读，无副作用。",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
  {"type": "function", "function": {
     "name": "search_knowledge",
     "description": "在本地医学知识库中检索条目，返回标题、摘要与来源链接。",
     "parameters": {"type": "object", "properties": {
        "query": {"type": "string"}, "top_k": {"type": "integer", "default": 3}}, "required": ["query"]}}}
]
```

**执行循环（关键，别写漏）**：

```python
for round in range(MAX_TOOL_ROUNDS):            # 3
    resp = client.chat.completions.create(..., tools=TOOLS, timeout=LLM_TIMEOUT)
    msg = resp.choices[0].message
    if not msg.tool_calls:
        return msg.content                     # 结束
    messages.append(msg)
    for call in msg.tool_calls:
        result = dispatch(call.function.name, json.loads(call.function.arguments))
        messages.append({"role": "tool", "tool_call_id": call.id,
                         "content": json.dumps(result, ensure_ascii=False)})
else:
    return fallback()                          # 达到上限，降级
```

- `dispatch` 里对未知工具名返回 `{"error": "unknown_tool"}`，**不要抛异常打断**。
- `json.loads` 失败 → 返回 `{"error":"bad_arguments"}`，让模型自己修。
- 工具抛异常 → `{"error": str(e)[:200]}`，同时 `logging.warning`。

### 9.3 熔断参数（P8）

| 参数 | 值 | 说明 |
|---|---|---|
| `MAX_TOOL_ROUNDS` | 3 | 超过即降级 |
| `LLM_TIMEOUT` | 25 s | 单次请求 |
| `TOTAL_BUDGET` | 40 s | 整轮交互，超时直接出离线报告 |
| `MAX_RETRY` | 1 | 仅对 429/5xx/超时 |
| `MAX_TOKENS` | 1200 | 报告不需要更长 |

### 9.4 降级矩阵

| 故障 | 行为 | 用户看到 |
|---|---|---|
| 无 API Key | 强制 offline | 橙色「离线演示模式」横幅 |
| 401/403 | 切换到 offline，并提示检查 Key | "模型鉴权失败，已切换为规则+模板模式" |
| 429/5xx | 重试 1 次，仍失败转 offline | "模型服务繁忙，已使用本地模板生成报告" |
| JSON 校验失败 2 次 | offline | "模型输出格式异常，已使用本地模板" |
| 知识库为空 | 继续，报告标注无来源 | "知识库暂无条目" |
| 规则文件加载失败 | **阻断**，显示配置错误 | 启动页红色错误 + 修复指引 |

---

## 10. LLM 层与离线模式

### 10.1 配置

`.env.example`：

```dotenv
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_TIMEOUT=25
MAX_TOOL_ROUNDS=3
ENABLE_VECTOR=0
LOG_LEVEL=INFO
```

- 只用 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` 三个必需项，其余有默认值。
- `load_config()` 返回 `Config`，**缺 Key 不报错**，只把 `mode` 设为 `offline`。
- `.gitignore` 必须含 `.env`、`__pycache__/`、`.streamlit/`、`*.log`。

### 10.2 客户端封装要点

1. 单例 `OpenAI(api_key=..., base_url=...)`，懒加载；
2. 所有异常收敛成 `LLMError(kind=...)`，`kind ∈ {auth, rate, timeout, network, format, unknown}`；
3. **不打印** `api_key`，日志里最多 `key[:4] + "***"`；
4. 记录每次调用的 `latency_ms / tokens / tool_rounds` 到本地 `logs/run.log`（截图可作"工程性"佐证）。

### 10.3 Prompt 结构（`agent/prompts.py`）

- `SYSTEM`: 角色 + 硬约束（不诊断、不开药、不编来源、必须调用工具、必须输出 JSON）+ 输出 schema；
- `SLOT_SUMMARY`: 把 `Slots` 渲染成"已知/未知"两栏，避免模型重复问；
- `REPORT_USER`: 用户原话 + `TriageResult` + `hits` 的 JSON；
- **禁止**把规则表全文塞进 prompt（模型会开始"推理"规则，进而覆盖规则结论）。

`SYSTEM` 里必须有这三句（可直接用）：

```text
1. 你只能整合给定的规则结果与知识库条目，不得引入库外医学事实。
2. risk.level 必须等于给定的 triage.level，不得修改。
3. 只输出 JSON，不要输出 Markdown 代码块以外的任何文字。
```

### 10.4 JSON 输出与修复（P9）

1. 首次请求用 `response_format={"type":"json_object"}`（若服务不支持则靠 prompt 约束）；
2. 解析失败：用 `json.loads` → 失败则用正则抓第一个 `{...}` 再试；
3. 仍失败：把错误 + 上次输出回传，明确说"只输出修正后的 JSON"，重试 1 次；
4. 仍失败：offline 降级。

### 10.5 离线模式（P10）

`agent/offline.py` 只做三件事：

1. `render_ask(slot_name, style) -> str`：从模板池取追问；
2. `build_report(slots, triage, hits) -> dict`：按 §5.6 schema 填字段，`limitations` 里固定加"本报告由本地规则与模板生成，未使用大语言模型"；
3. `render_red_flag(triage) -> str`：紧急卡文案。

**必须显性**：
- 页面顶部固定横幅（橙色）：「⚠️ 离线演示模式：当前使用本地规则与固定模板，**未调用大模型**，输出不代表模型推理能力」；
- 报告中每个区块右上角小字标注生成方式（`规则模板` / `模型生成`）；
- 演示视频里主动说明这一点（加分项，不是减分项）。

---

## 11. 报告与前端规格

### 11.1 报告 8 个区块（顺序固定）

| # | 区块 | 内容要求 | 标签 |
|---|---|---|---|
| 1 | 主要症状 | 用户原话摘要，不改写 | `[用户提供]` |
| 2 | 已收集信息 | 时长/严重度/伴随/背景（表格化） | `[用户提供]` |
| 3 | 仍缺失信息 | 缺哪几项 + 为什么重要 | `[系统状态]` |
| 4 | 风险分层 | 等级 + 逐条依据（对应 rule.message） | `[规则筛查]` |
| 5 | 建议下一步 | 3–5 条可执行动作 | `[规则筛查]` + `[模型解释]` |
| 6 | 相关知识摘要 | 每条：标题 + 一句话 + 链接 | `[知识库]` |
| 7 | 需警惕的变化 | 出现哪些情况要升级就医 | `[模型解释]` |
| 8 | 局限与免责 | 固定文案（附录 A） | — |

### 11.2 三色风险卡（P12）

| 等级 | 颜色 | 图标 | 首句 |
|---|---|---|---|
| EMERGENCY | 红 | 🚨 | "以下情况需要**立即**处理" |
| URGENT | 橙 | ⚠️ | "建议在 **24 小时内**就医" |
| ROUTINE | 蓝 | ℹ️ | "目前未发现规则覆盖的紧急信号，可先居家观察" |
| INSUFFICIENT | 灰 | ❓ | "现有信息不足以判断风险等级" |

> ROUTINE 的措辞必须带"未发现规则覆盖的紧急信号"而不是"你是安全的"——这是 P2 的关键差别，答辩会被问。

### 11.3 Streamlit 结构（P11）

```python
st.set_page_config(page_title="MedAgent 智能诊疗辅助", page_icon="🩺", layout="centered")
# 顺序：标题/简介 → 模式横幅 → 免责声明折叠框 → 对话区 → 进度/风险区 → 输入框 → 报告区 → 底部按钮
```

**session_state 键表**（初始化函数 `init_state()` 在 `app.py` 顶部调用一次）：

| 键 | 类型 | 写入时机 | 清空时 |
|---|---|---|---|
| `session` | `Session` | 每轮结束 | 重建 |
| `messages` | `list[dict]`（仅渲染用） | 每轮 | `[]` |
| `mode` | `"online"/"offline"` | 启动 | 重算 |
| `show_report` | `bool` | 报告生成后 | `False` |
| `last_error` | `str|None` | 异常时 | `None` |
| `api_ok` | `bool` | 启动探活 | 重算 |

**三条实现纪律**：
1. **渲染函数里不调 LLM**。所有模型调用放在 `if st.button(...)` 或 `st.form` 的提交分支里，否则每次 rerun 都会重复计费（这是最常见的坑）。
2. 输入用 `st.chat_input` + `st.chat_message`；历史消息来自 `st.session_state.messages`。
3. "重新开始"按钮：清空 §上表所有键 → `st.rerun()`；同时清空 `agent` 里的缓存（如果有 `@st.cache_resource` 的 client，保留，但重置计数）。

**进度展示**：4 个 checkbox 样式的槽位进度（主诉 / 时长 / 严重度 / 伴随），实时更新，评委一眼能看懂"系统在收集什么"。

### 11.4 异常提示（P18）

| 情况 | 展示 |
|---|---|
| 无 API Key | 顶部橙色 info：「未检测到 LLM_API_KEY，已进入离线演示模式。配置方法见 README。」 |
| 调用失败 | `st.warning`：「模型调用失败（{kind}），已使用本地模板生成报告。可稍后重试。」 |
| 知识库为空 | `st.info`：「知识库暂无匹配条目，以下建议仅基于规则筛查。」 |
| 规则加载失败 | `st.error` + 具体字段 + "请检查 knowledge/rules.json" |
| 空输入 | 不提交，提示"请先描述一下你的不适" |

---

## 12. 十天执行计划（含分工）

> 原方案按"阶段"划分，容易拖到最后才集成。这里改成天级、带**完成判据**。【P14】
> 假定 D1 = 开工日，D10 = 冻结提交版，D11–D12 只录视频和写文档，**不改代码**。

| 天 | 目标（一句话） | A 集成 | B 知识/规则 | C 前端/测试 | D 文档/产品 | 完成判据 |
|---|---|---|---|---|---|---|
| D1 | 骨架 + 契约 | `contracts.py`、目录、`requirements.txt`、`.env.example` | 读规则来源，列 12 条规则草案 | 空 `app.py` 能跑 | 建 git 仓库、README 骨架、拉群定节奏 | `streamlit run app.py` 打开是白页但不报错；`contracts.py` 已 push |
| D2 | 规则引擎可用 | `triage_rules.py`（加载 + 匹配 + 否定） | `knowledge/rules.json` 12 条 + 来源编号 | 写 `test_rules.py`（红灯） | 写 6 条合成案例 | `pytest tests/test_rules.py` 有 8 个用例，≥5 绿 |
| D3 | **首个闭环可录屏** | `controller.py` 最小版：输入→规则→离线报告 | 3 条知识条目 | 页面接上：输入框 + 风险卡 | 录 40 秒屏（内部用，不交） | 输入"胸痛"→立即红色卡；输入"咳嗽三天"→追问 |
| D4 | 知识检索 | `medical_search.py` 接口对接 | 12 条知识条目完成 + 自检脚本 | `test_retrieval.py` | 开始写 architecture.md | 检索能返回带 URL 的条目；空查询返回 `[]` |
| D5 | 在线模型接通 | `llm.py` + 工具循环 + JSON 校验 | — | 页面加模式横幅、异常提示 | 写 .env 配置说明 | 配置真实 Key 能出报告；断网/错 Key 自动降级 |
| D6 | 追问策略 | 槽位抽取 + 3 轮上限 + 不重复问 | 追问模板文案润色（医学准确性） | `test_controller.py` | 补 project_description.md | 缺信息时最多问 3 轮，然后出 INSUFFICIENT 报告 |
| D7 | 打磨与加固 | 熔断、日志脱敏、重试 | 规则复核（找老师/医学生看一遍措辞） | 全量跑 18 条用例 | 写 demo_script.md | `pytest -q` 全绿；日志无 Key、无原文 |
| D8 | 演示打磨 | 前端视觉与文案 | 补 3–5 条知识条目 | 3 个演示案例端到端走通 | 写视频分镜、准备截图 | 三个案例各录一遍，无报错 |
| D9 | 干净环境验证 | 建新 venv 按 README 装 | 检查所有 URL 可打开 | 复跑测试 | 整理提交清单 | 新环境 30 分钟内跑起来 |
| D10 | 冻结 | 只改 bug | 只改错别字 | 只改文案 | 录制并剪辑视频（≤5 分钟） | tag `v1.0`，打包 zip / 推仓库 |

**关键节奏**：D3 必须有闭环（哪怕丑）；D5 之前不要碰向量检索、不要做登录、不要接数据库。

---

## 13. 测试规格

### 13.1 文件与运行

```bash
pytest -q                      # 期望：xx passed
pytest tests/test_rules.py -v  # 单模块
```

`requirements.txt` 里加 `pytest`。CI 可选（GitHub Actions 30 行模板），不加分也不扣分，但**能截图**。

### 13.2 18 条用例（直接抄进 `tests/cases.json`）

| # | 输入（合成案例） | 期望 level | 期望行为断言 |
|---|---|---|---|
| 1 | "胸口压着疼，出汗，持续 20 分钟" | emergency | `matched_rules` 含 R001；`red_flag_actions` 非空 |
| 2 | "突然左边手脚没力气，说话不清" | emergency | 含 R002 |
| 3 | "喘不上气，躺下更严重，嘴唇发紫" | emergency | 含 R003 |
| 4 | "刚才抽了一次，现在人有点迷糊" | emergency | 含 R004 |
| 5 | "吐了一大口血" | emergency | 含 R005 |
| 6 | "肚子痛得直不起腰，按下去更痛" | emergency | 含 R006 |
| 7 | "不想活了，已经想好怎么做了" | emergency | 含 R007，且输出危机热线 |
| 8 | "吃了花生之后喉咙发紧，脸上起包" | emergency | 含 R008 |
| 9 | "发烧 39.5 度两天了" | urgent | 含 R009 |
| 10 | "宝宝 8 个月，发烧 38.2 度" | urgent | 含 R010；`modifiers_applied` 含 infant |
| 11 | "怀孕 30 周，肚子一阵阵痛，有点出血" | emergency/urgent | 含 R011，且 ≥urgent |
| 12 | "拉肚子一天七八次，站起来头晕" | urgent | 含 R012 |
| 13 | "**我没有胸痛**，就是有点咳嗽三天了" | 非 emergency | 断言 `negations` 含"胸痛"；level ∉ {emergency} |
| 14 | "**如果我胸痛**该怎么办？" | 非 emergency | 只检索，不升级 |
| 15 | "不舒服" | insufficient | `missing_slots` 非空；`ask_count` 之后仍不上报结论 |
| 16 | "咳嗽三天，有点痰，不发烧"（信息齐） | routine 或 insufficient | level ≠ emergency；且若有知识条目则 `hits` 非空 |
| 17 | 知识库置空后查询"量子力学" | — | `search()` 返回 `[]`，且报告 `knowledge_summary == []`，无异常 |
| 18 | API Key 设为 `sk-invalid` | — | 不抛异常；`mode` 切换到 offline；有 warning 文案 |

补充 3 条"结构性"测试：

- `test_rules.py::test_no_llm_import`：断言 `tools/triage_rules.py` 源码不含 `openai`；
- `test_rules.py::test_rule_schema`：所有规则字段合法、`sources` 非空；
- `test_retrieval.py::test_all_urls_present`：`status=verified` 的条目 `source_url` 以 `http` 开头。

### 13.3 测试纪律

- **不许 mock 掉规则引擎**（那等于没测）；
- 允许 mock 的是 `OpenAI` 客户端；
- 测试数据全部合成，禁止真实姓名/电话/病历号；
- 报告里写测试结果时，**贴终端原始输出截图**，不要手写"通过率 100%"。

---

## 14. Demo 视频脚本

总长 **4–5 分钟**，三幕，一镜到底优先（减少剪辑破绽）。

| 时间 | 内容 | 要点 |
|---|---|---|
| 0:00–0:30 | 问题陈述 | 一句话："普通人分不清该不该去医院，MedAgent 帮你把症状整理成一份能带着去看医生的报告。" |
| 0:30–0:50 | 界面与定位 | 指出顶部免责声明、离线/在线模式标识 |
| 0:50–2:10 | 案例 1：普通症状多轮对话 | "咳嗽三天" → 系统追问时长/严重度/伴随 → 出蓝色 ROUTINE 报告 → 展示知识来源链接可点 |
| 2:10–3:10 | 案例 2：紧急信号 | 输入"胸口压着疼还出汗" → **立刻**红色卡（强调"没有等待追问、没有等待检索"）→ 展示规则 id 与来源 |
| 3:10–3:50 | 案例 3：信息不足 | 输入"不舒服" → 追问 3 轮 → 灰色 INSUFFICIENT 报告，明确写"无法充分评估" |
| 3:50–4:20 | 技术亮点 | 规则与模型解耦、工具真实调用日志、`pytest` 真实输出（录屏滚一遍） |
| 4:20–4:50 | 局限与计划 | 主动说：未做临床验证、知识库规模有限、下一步接入更多来源与医生复核 |

**录制清单**：分辨率 1920×1080、字号调大、鼠标移动慢、提前准备 3 个案例的输入文本（复制粘贴，别现场打字）。

---

## 15. 提交物清单

- [ ] 代码仓库（公开可读 / 或 zip，含 `.git` 历史更好）
- [ ] `README.md`：项目简介、功能、安装、运行、配置、目录说明、已知限制
- [ ] `docs/project_description.md`：目标、Demo 功能、系统设计（含架构图）、进展、后续计划
- [ ] `docs/architecture.md`：模块图 + 数据流 + 规则/检索/模型的分工说明
- [ ] `docs/demo_script.md`：视频脚本
- [ ] `docs/baseline.md`：本文件
- [ ] `requirements.txt` / `.env.example` / `.gitignore`
- [ ] 测试输出截图（`pytest -q`）
- [ ] 视频（mp4，≤5 min，≤200MB）
- [ ] `knowledge/` 下每条来源的截图或存档说明（可选，显著加分）

---

## 16. 验收清单（DoD）

**功能**

- [ ] 无 Key 启动 → 橙色离线横幅 → 全流程可走完
- [ ] 有 Key → 多轮对话 + 至少 1 次真实工具调用（日志可证）
- [ ] 危险信号 → 1 次交互内红色卡，无追问、无检索阻塞
- [ ] 信息不足 → 3 轮内追问，之后出 INSUFFICIENT
- [ ] 报告 8 区块齐全，三类标签齐全
- [ ] 每条知识引用可点击且与库内 URL 完全一致
- [ ] "重新开始"彻底清空（含 report / triage / ask_count）

**质量**

- [ ] `pytest -q` 全绿，18 条用例全覆盖
- [ ] 规则文件自检通过；无 `pending` 条目进入报告
- [ ] 日志无 Key、无完整用户原文
- [ ] `.env` 未提交（`git log --stat` 自查）
- [ ] 新环境按 README 30 分钟可跑

**合规**

- [ ] 全文无"确诊/准确率/临床验证"类表述
- [ ] 无药物剂量建议
- [ ] 首屏与报告页脚均有免责声明
- [ ] 演示数据全部合成

---

## 17. 常见坑

1. **Streamlit 重复调用**：把 `llm.chat()` 写在渲染路径里 → 每次交互都调一次 API。只在按钮分支里调。
2. **`st.session_state` 存了不可序列化对象**：存 `Session` dataclass 没问题；存 `OpenAI` client 用 `@st.cache_resource`。
3. **中文 JSON 乱码**：`json.dump(..., ensure_ascii=False, indent=2)`，文件用 UTF-8 无 BOM。
4. **`@st.cache_data` 缓存了带时间的函数**：规则/知识加载可以缓存，但"重新开始"要 `st.cache_data.clear()`。
5. **Windows 换行/路径**：知识库路径用 `pathlib.Path(__file__).parent`，别写死 `E:\`。
6. **依赖漂移**：`requirements.txt` 全部钉版本（`streamlit==1.3x.x`、`openai>=1.30`），否则评委环境装不上。
7. **模型返回 Markdown 包裹的 JSON**：解析前先去掉 ```json 围栏。
8. **工具调用死循环**：模型反复调同一个工具 → `MAX_TOOL_ROUNDS` 兜底，且对重复 `(name, args)` 直接返回缓存结果。
9. **规则一改就误报**：加规则必须同时加一条负例测试（"我没有…"）。
10. **演示时网络抖动**：提前录好备用视频；现场先跑离线模式证明稳定性。

---

## 附录 A 固定文案

**首屏免责声明（折叠框，默认展开一次）**

```text
本工具用于健康信息整理与就医导航，不能替代医生面诊，不提供诊断、处方或治疗方案。
报告中的风险分层来自固定的规则筛查，可能漏判或误判；知识条目来自公开资料，可能存在更新滞后。
如出现剧烈胸痛、呼吸困难、意识改变、大量出血等情况，请立即拨打 120 或前往最近医院急诊。
```

**报告页脚**

```text
本报告由 MedAgent 依据你提供的信息、固定风险规则与公开知识条目生成，不构成医疗诊断或治疗建议。
如果你对症状有任何担心，或症状持续加重，请及时就医。
生成方式：{规则模板 | 模型生成 + 规则校验} ｜ 规则版本：{rules.json vX} ｜ 知识库版本：{YYYY-MM-DD}
```

**EMERGENCY 卡首句**

```text
你描述的情况中包含需要立即处理的信号，请现在拨打 120 或让家人陪同前往最近医院急诊。
```

**INSUFFICIENT 卡首句**

```text
目前收集到的信息还不足以判断风险等级——这不等于"没问题"。以下是你还需要补充的信息。
```

**危机干预（R007 触发时必带）**

```text
如果你现在有伤害自己的想法，请立即联系身边可信任的人陪伴你，并拨打当地心理援助热线或 120。
你不需要独自面对这件事。
```

> 提交前请核实当地心理援助热线的**当前有效号码**，写不清就只写"当地心理援助热线 / 120"，**不要编号码**。

---

## 附录 B 规则来源与待核实标注

**来源编号表**（`sources` 字段引用这里的编号）：

| 编号 | 类型 | 用途 | 状态 |
|---|---|---|---|
| S-ER-TRIAGE | 急诊预检分诊类共识/规范 | 危险信号分级思路 | 待核实具体文件与年份 |
| S-STROKE-FAST | 卒中公众识别（FAST / 中风 120） | R002 | 待核实官方科普页链接 |
| S-FEVER-CHILD | 儿童发热管理类官方科普 | R010 | 待核实 |
| S-PREG-ALERT | 孕产期危险信号类官方科普 | R011 | 待核实 |
| S-DEHYDRATION | 脱水/腹泻家庭管理类官方科普 | R012 | 待核实 |
| S-CRISIS | 心理危机干预官方指引 | R007 | 待核实 |

**标注纪律**：
1. 每条规则在 `rules.json` 的 `sources` 里写编号，`docs/architecture.md` 里维护"编号 → 具体出处 → 访问日期 → 适用范围 → 局限"的表；
2. **拿不到确切出处就标 `待核实`**，并在文档里写"本规则为工程保守阈值，非指南原文"；
3. 严禁写"依据《XXX 指南（2023）》第 4.2 条"这种精确到条款但无法核对的引用——这是评审最容易抓的点；
4. B 在 D7 前完成一轮"措辞复核"，最好请医学背景的人看一眼（哪怕只是学长）。

---

## 附录 C 合成案例模板

`tests/cases.json` 单条格式：

```json
{
  "id": "case_01",
  "persona": "35 岁男性，办公室职员（虚构）",
  "turns": ["胸口压着疼，还一直出汗，大概二十分钟了"],
  "expect_level": "emergency",
  "expect_rules": ["R001"],
  "expect_behavior": "immediate_red_card",
  "notes": "验证危险信号不被追问延迟"
}
```

**六个必做案例**（对应视频三幕 + 三个边界）：

1. `case_01` 持续胸痛 → emergency，0 追问；
2. `case_02` 咳嗽三天、不发热 → 追问 → routine；
3. `case_03` "不舒服" → 3 轮追问 → insufficient；
4. `case_04` "我没有胸痛，就是咳嗽" → 不误报；
5. `case_05` "8 个月宝宝发烧 38.2℃" → urgent + infant 修饰；
6. `case_06` 空知识库环境 → 报告无引用、提示明确。

---

**版本**：v1.0 ｜ **冻结日期**：待 D1 确认 ｜ **维护人**：A（集成）+ D（文档）
**变更记录**：任何对 §5 契约的修改必须在此追加一行（日期 / 字段 / 原因 / 影响文件）。
