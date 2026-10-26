"""MedAgent Streamlit 前端（BASELINE.md §11）。

纪律：
* 渲染路径里不调用模型，所有调用发生在 st.chat_input 提交分支；
* 状态只放在 st.session_state，键表见 §11.3；
* 任何异常都要变成用户能看懂的提示，不允许白屏。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from agent.controller import AgentController
from agent.llm import Config, load_config
from contracts import (
    MAX_ASK_ROUNDS,
    SLOT_LABELS,
    Mode,
    Reply,
    RiskLevel,
    SourceTag,
)
from tools.medical_search import get_knowledge_base
from tools.triage_rules import load_rules

APP_TITLE = "MedAgent · 智能诊疗辅助"
VERSION = "v1.0"

DISCLAIMER = (
    "本工具用于健康信息整理与就医导航，**不能替代医生面诊**，不提供诊断、处方或治疗方案。\n\n"
    "报告中的风险分层来自固定的规则筛查，可能漏判或误判；知识条目来自公开资料，可能存在更新滞后。\n\n"
    "如出现剧烈胸痛、呼吸困难、意识改变、大量出血等情况，请立即拨打 120 或前往最近医院急诊。"
)


# --------------------------------------------------------------------------- #
# 状态
# --------------------------------------------------------------------------- #
def init_state() -> None:
    if "config" not in st.session_state:
        st.session_state.config = load_config()
    if "controller" not in st.session_state:
        st.session_state.controller = AgentController(st.session_state.config)
        st.session_state.messages = [
            {"role": "assistant", "content": st.session_state.controller.greeting()}
        ]
    st.session_state.setdefault("report", None)
    st.session_state.setdefault("mode", st.session_state.config.mode.value)
    st.session_state.setdefault("last_error", None)


def restart() -> None:
    controller: AgentController = st.session_state.controller
    controller.reset()
    st.session_state.messages = [{"role": "assistant", "content": controller.greeting()}]
    st.session_state.report = None
    st.session_state.mode = st.session_state.config.mode.value
    st.session_state.last_error = None


# --------------------------------------------------------------------------- #
# 渲染片段
# --------------------------------------------------------------------------- #
def render_header() -> None:
    st.title("🩺 MedAgent")
    st.caption(
        "基于「规则引擎 + 本地知识库 + 大语言模型」的中文症状信息整理与就医导航助手 ｜ "
        "不做诊断，不开药，不替代医生"
    )


def render_mode_banner(config: Config) -> None:
    if config.mode is Mode.OFFLINE:
        st.warning(
            "⚠️ **离线演示模式**：当前使用本地规则与固定模板，**未调用大模型**，"
            "输出不代表模型推理能力。配置 `LLM_API_KEY` 后自动切换为在线模式。",
            icon="⚠️",
        )
    else:
        st.info(f"在线模式 ｜ 模型：`{config.model}` ｜ 风险分级仍由本地规则引擎决定", icon="✅")


def render_disclaimer() -> None:
    with st.expander("⚠️ 使用前请阅读：免责声明", expanded=False):
        st.markdown(DISCLAIMER)


def render_progress(controller: AgentController) -> None:
    slots = controller.session.slots
    triage = controller.session.triage
    st.markdown("**评估进度**")
    cols = st.columns(4)
    items = [
        ("主要症状", slots.chief_complaint),
        ("持续时间", slots.duration),
        ("严重程度", f"{slots.severity}/10" if slots.severity is not None else None),
        ("伴随症状", "、".join(slots.associated) if slots.associated else None),
    ]
    for col, (label, value) in zip(cols, items):
        with col:
            st.metric(label=label, value=value or "待补充")
    if triage and triage.missing_slots:
        left = MAX_ASK_ROUNDS - controller.session.ask_count
        st.caption(
            "还需了解："
            + "、".join(SLOT_LABELS.get(item, item) for item in triage.missing_slots)
            + f"（最多再追问 {max(left, 0)} 轮）"
        )


def render_risk_card(triage) -> None:
    if triage is None:
        return
    level: RiskLevel = triage.level
    box = {
        RiskLevel.EMERGENCY: st.error,
        RiskLevel.URGENT: st.warning,
        RiskLevel.ROUTINE: st.info,
        RiskLevel.INSUFFICIENT: st.info,
    }[level]
    box(f"{level.icon} **{level.cn}**\n\n{level.first_sentence}")

    if triage.matched_rules:
        with st.expander(f"规则命中详情（{len(triage.matched_rules)} 条）"):
            st.markdown("**命中规则：** " + "、".join(f"`{rid}`" for rid in triage.matched_rules))
            for reason in triage.reasons:
                st.markdown(f"- {reason}")
            if triage.modifiers_applied:
                st.markdown("**人群修饰：** " + "、".join(triage.modifiers_applied))
            st.caption(triage.screening_note)


def render_report(report: dict[str, Any], mode: str) -> None:
    if not report:
        return
    level_value = str((report.get("risk") or {}).get("level", "insufficient"))
    try:
        level = RiskLevel(level_value)
    except ValueError:
        level = RiskLevel.INSUFFICIENT

    st.subheader("评估报告")
    generated = "规则模板生成" if mode == Mode.OFFLINE.value else "模型生成 + 规则校验"
    st.caption(f"{level.icon} {level.cn} ｜ 生成方式：{generated} ｜ {APP_TITLE} {VERSION}")

    st.markdown(f"**主要症状** {SourceTag.USER.cn}\n\n{report.get('chief_complaint') or '未提供'}")

    collected = report.get("collected") or {}
    st.markdown(f"**已收集信息** {SourceTag.USER.cn}")
    st.markdown(
        "\n".join(
            [
                f"- 持续时间：{collected.get('duration', '未提供')}",
                f"- 严重程度：{collected.get('severity', '未提供')}",
                f"- 伴随症状：{'、'.join(collected.get('associated') or ['未提供'])}",
                f"- 背景信息：{'、'.join(collected.get('background') or ['未提供'])}",
            ]
        )
    )

    missing = report.get("missing") or []
    st.markdown(f"**仍缺失的信息** {SourceTag.USER.cn}")
    st.markdown("\n".join(f"- {item}" for item in missing) if missing else "- 关键信息已收集完整")

    st.markdown(f"**风险分层与依据** {SourceTag.RULE.cn}")
    st.markdown(f"- 等级：{level.cn}")
    for item in (report.get("risk") or {}).get("basis") or []:
        st.markdown(f"- {item}")

    st.markdown(f"**建议的下一步** {SourceTag.RULE.cn}")
    for item in report.get("next_steps") or []:
        st.markdown(f"- {item}")

    st.markdown(f"**健康知识摘要** {SourceTag.KB.cn}")
    summary = report.get("knowledge_summary") or []
    if not summary:
        st.info("本次未检索到可靠知识条目，以上建议仅基于规则筛查。")
    for item in summary:
        badge = "站点入口" if str(item.get("url", "")).count("/") <= 3 else "直达页面"
        st.markdown(f"- [{item.get('title')}]({item.get('url')})（{badge}）— {item.get('one_line', '')}")

    st.markdown(f"**需警惕的变化** {SourceTag.MODEL.cn}")
    for item in report.get("red_flags_to_watch") or []:
        st.markdown(f"- {item}")

    st.markdown("**局限性与免责声明**")
    for item in report.get("limitations") or []:
        st.markdown(f"- {item}")
    st.caption(DISCLAIMER.replace("\n\n", " "))


def render_sources(controller: AgentController) -> None:
    hits = controller.session.hits
    if not hits:
        return
    with st.expander("本次引用的知识来源"):
        for hit in hits:
            st.markdown(f"- [{hit.title}]({hit.url}) — {hit.org}（相关度 {hit.score:.2f}）")


# --------------------------------------------------------------------------- #
# 侧边栏
# --------------------------------------------------------------------------- #
def render_sidebar(config: Config) -> None:
    with st.sidebar:
        st.markdown("### 会话")
        if st.button("🔄 重新开始", use_container_width=True):
            restart()
            st.rerun()

        st.divider()
        st.markdown("### 运行信息")
        st.markdown(f"- 模式：{'离线演示' if config.mode is Mode.OFFLINE else '在线'}")
        st.markdown(f"- 模型：`{config.model}`" + ("（未配置）" if config.mode is Mode.OFFLINE else ""))
        st.markdown(f"- Key：`{config.masked_key}`")
        try:
            rules = load_rules()
            st.markdown(f"- 风险规则：{len(rules)} 条")
        except ValueError as exc:
            st.markdown(f"- 风险规则：⚠️ 加载失败")
            st.caption(str(exc)[:200])
        try:
            stats = get_knowledge_base().stats()
            st.markdown(f"- 知识条目：{stats['total']} 条（可引用 {stats['verified']}）")
        except Exception as exc:  # pragma: no cover
            st.markdown("- 知识条目：⚠️ 加载失败")
            st.caption(str(exc)[:200])

        st.divider()
        st.markdown("### 使用提示")
        st.markdown(
            "1. 用一句话描述最不舒服的地方\n"
            "2. 回答系统追问（最多 3 轮）\n"
            "3. 查看报告与来源链接\n"
            "4. 出现危险信号会立即弹红色提示"
        )
        st.caption(f"MedAgent {VERSION} ｜ 规则与知识库版本见 docs/architecture.md")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🩺", layout="centered")
    init_state()

    config: Config = st.session_state.config
    controller: AgentController = st.session_state.controller

    render_header()
    render_mode_banner(config)
    render_disclaimer()
    render_sidebar(config)

    render_progress(controller)

    # 历史消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 风险卡片 / 报告
    if controller.session.triage is not None:
        render_risk_card(controller.session.triage)
    render_sources(controller)
    if st.session_state.report:
        with st.container(border=True):
            render_report(st.session_state.report, st.session_state.mode)

    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    finished = controller.session.finished
    prompt = st.chat_input(
        "描述你的症状，例如：咳嗽三天，有点痰" if not finished else "本次评估已结束，请点击左侧「重新开始」",
        disabled=finished,
    )

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("正在整理信息…"):
                try:
                    reply: Reply = controller.handle(prompt)
                    st.session_state.last_error = None
                except Exception as exc:  # 兜底，绝不让页面白屏
                    st.session_state.last_error = f"处理失败：{type(exc).__name__}。请点击「重新开始」重试。"
                    st.error(st.session_state.last_error)
                    return
            st.markdown(reply.text)

        st.session_state.messages.append({"role": "assistant", "content": reply.text})
        if reply.report:
            st.session_state.report = reply.report
        st.session_state.mode = reply.mode
        st.rerun()


if __name__ == "__main__":
    main()
