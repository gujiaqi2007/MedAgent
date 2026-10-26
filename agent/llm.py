"""模型层：配置、客户端封装、工具调用循环、报告 JSON 校验（BASELINE.md §10）。"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from contracts import (
    LLM_TIMEOUT,
    MAX_TOKENS,
    MAX_TOOL_ROUNDS,
    SLOT_LABELS,
    KnowledgeHit,
    Mode,
    RiskLevel,
    Slots,
    TriageResult,
)
from agent import prompts

logger = logging.getLogger(__name__)

try:  # python-dotenv 是软依赖
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:  # type: ignore[misc]
        return False

try:
    import openai  # noqa: F401
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - 允许未装 openai 时跑离线模式
    OpenAI = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.2
    timeout: int = LLM_TIMEOUT
    max_tool_rounds: int = MAX_TOOL_ROUNDS
    max_tokens: int = MAX_TOKENS
    enable_vector: bool = False
    log_level: str = "INFO"

    @property
    def mode(self) -> Mode:
        return Mode.ONLINE if self.api_key.strip() else Mode.OFFLINE

    @property
    def masked_key(self) -> str:
        if not self.api_key:
            return "(未配置)"
        return self.api_key[:4] + "***"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = env or os.environ
        return cls(
            api_key=(env.get("LLM_API_KEY") or "").strip(),
            base_url=(env.get("LLM_BASE_URL") or "https://api.deepseek.com/v1").strip(),
            model=(env.get("LLM_MODEL") or "deepseek-chat").strip(),
            temperature=float(env.get("LLM_TEMPERATURE") or 0.2),
            timeout=int(env.get("LLM_TIMEOUT") or LLM_TIMEOUT),
            max_tool_rounds=int(env.get("MAX_TOOL_ROUNDS") or MAX_TOOL_ROUNDS),
            max_tokens=int(env.get("MAX_TOKENS") or MAX_TOKENS),
            enable_vector=(env.get("ENABLE_VECTOR") or "0") == "1",
            log_level=(env.get("LOG_LEVEL") or "INFO").upper(),
        )


def load_config(env_path: str | None = None) -> Config:
    """读取 .env 与环境变量。缺 Key 不报错，只降级为离线模式。"""
    load_dotenv(env_path) if env_path else load_dotenv()
    return Config.from_env()


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #
class LLMError(RuntimeError):
    """统一异常。kind ∈ auth | rate | timeout | network | format | tool_limit | unknown"""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind
        self.message = message

    @property
    def cn(self) -> str:
        return {
            "auth": "鉴权失败（请检查 LLM_API_KEY）",
            "rate": "模型服务限流",
            "timeout": "模型响应超时",
            "network": "网络连接失败",
            "format": "模型输出格式异常",
            "tool_limit": "工具调用次数超限",
            "not_configured": "未配置模型 API",
            "unknown": "模型调用异常",
        }.get(self.kind, "模型调用异常")


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
class LLMClient:
    """OpenAI 兼容客户端。工具调用循环真实执行，绝不只声明不执行（P8）。"""

    def __init__(self, config: Config, opener: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._opener = opener
        self._client: Any = None

    # ------------------------------------------------------------------ #
    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if OpenAI is None:
            raise LLMError("not_configured", "未安装 openai 包，只能使用离线模式")
        if not self.config.api_key:
            raise LLMError("not_configured", "LLM_API_KEY 为空")
        try:
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                timeout=self.config.timeout,
                max_retries=0,  # 重试由我们控制，避免叠加
            )
        except Exception as exc:  # pragma: no cover
            raise LLMError("unknown", str(exc)[:200]) from exc
        return self._client

    # ------------------------------------------------------------------ #
    def _chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None):
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        started = time.time()
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _to_llm_error(exc) from exc
        logger.info(
            "llm call model=%s latency=%.0fms",
            self.config.model,
            (time.time() - started) * 1000,
        )
        return response

    # ------------------------------------------------------------------ #
    def run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        dispatch: Callable[[str, dict[str, Any]], Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], int]:
        """跑完整的工具调用循环，返回 (最终文本, 工具调用日志, 轮次)。"""
        tools = tools if tools is not None else prompts.TOOL_DEFINITIONS
        messages = list(messages)
        log: list[dict[str, Any]] = []

        for round_index in range(1, self.config.max_tool_rounds + 1):
            response = self._chat(messages, tools)
            try:
                message = response.choices[0].message
            except (AttributeError, IndexError) as exc:  # pragma: no cover
                raise LLMError("format", "响应结构异常") from exc

            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                return (getattr(message, "content", "") or "", log, round_index)

            messages.append(_assistant_message(message))
            for call in tool_calls:
                name = getattr(getattr(call, "function", None), "name", "")
                raw_args = getattr(getattr(call, "function", None), "arguments", "") or "{}"
                try:
                    args = json.loads(raw_args)
                    if not isinstance(args, dict):
                        raise ValueError("arguments 必须是 JSON 对象")
                except (json.JSONDecodeError, ValueError):
                    result: Any = {"error": "bad_arguments", "hint": "参数必须是合法 JSON 对象"}
                    args = {}
                else:
                    try:
                        result = dispatch(name, args)
                    except Exception as exc:  # 工具异常不打断循环
                        logger.warning("tool %s failed: %s", name, exc)
                        result = {"error": str(exc)[:200]}

                log.append({"round": round_index, "name": name, "args": args, "ok": "error" not in result if isinstance(result, dict) else True})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(call, "id", "") or f"call_{round_index}",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        raise LLMError("tool_limit", f"超过 {self.config.max_tool_rounds} 轮工具调用")


# --------------------------------------------------------------------------- #
# 报告解析与校验（P9）
# --------------------------------------------------------------------------- #
REPORT_KEYS = (
    "chief_complaint",
    "collected",
    "missing",
    "risk",
    "next_steps",
    "knowledge_summary",
    "red_flags_to_watch",
    "limitations",
)

FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise LLMError("format", "模型返回空内容")
    raw = FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("format", "找不到 JSON 对象")
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("format", str(exc)[:120]) from exc
    if not isinstance(data, dict):
        raise LLMError("format", "顶层必须是 JSON 对象")
    return data


def validate_report(
    data: dict[str, Any],
    triage: TriageResult,
    hits: list[KnowledgeHit],
    slots: Slots,
) -> tuple[dict[str, Any], list[str]]:
    """校验并修正模型输出。规则结果永远优先（§5.6）。"""
    warnings: list[str] = []
    report = dict(data) if isinstance(data, dict) else {}

    for key in REPORT_KEYS:
        report.setdefault(key, [] if key in {"missing", "next_steps", "knowledge_summary", "red_flags_to_watch", "limitations"} else "")

    if not isinstance(report.get("collected"), dict):
        report["collected"] = {}
    risk = report.get("risk")
    if not isinstance(risk, dict):
        risk = {}
    report["risk"] = risk

    # 1) 风险等级以规则为准
    wanted = triage.level.value
    if risk.get("level") != wanted:
        warnings.append(f"模型给出的风险等级 {risk.get('level')!r} 与规则不一致，已采用规则结果 {wanted!r}")
        risk["level"] = wanted

    basis = risk.get("basis")
    if not isinstance(basis, list) or not basis:
        risk["basis"] = list(triage.reasons) or [triage.screening_note]

    # 2) 缺失信息用规则结果覆盖
    report["missing"] = [SLOT_LABELS.get(item, item) for item in triage.missing_slots]

    # 3) 知识条目只保留本次真实命中的
    allowed = {hit.id: hit for hit in hits}
    cleaned: list[dict[str, Any]] = []
    for item in report.get("knowledge_summary") or []:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id", ""))
        if entry_id not in allowed:
            warnings.append(f"已删除模型编造的知识条目：{entry_id or '(空 id)'}")
            continue
        hit = allowed[entry_id]
        cleaned.append(
            {
                "id": hit.id,
                "title": hit.title,
                "url": hit.url,  # URL 永远用库里的原值
                "one_line": str(item.get("one_line") or hit.summary)[:120],
            }
        )
    report["knowledge_summary"] = cleaned

    # 4) 列表字段类型保护
    for key in ("next_steps", "red_flags_to_watch", "limitations"):
        value = report.get(key)
        if not isinstance(value, list):
            report[key] = [str(value)] if value else []
        report[key] = [str(item) for item in report[key] if str(item).strip()][:8]

    if warnings:
        report["limitations"] = list(report["limitations"]) + warnings

    return report, warnings


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _assistant_message(message: Any) -> dict[str, Any]:
    try:
        dumped = message.model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    except Exception:  # pragma: no cover
        pass
    return {
        "role": "assistant",
        "content": getattr(message, "content", "") or "",
        "tool_calls": [
            {
                "id": getattr(call, "id", ""),
                "type": "function",
                "function": {
                    "name": getattr(getattr(call, "function", None), "name", ""),
                    "arguments": getattr(getattr(call, "function", None), "arguments", "{}"),
                },
            }
            for call in (getattr(message, "tool_calls", None) or [])
        ],
    }


def _to_llm_error(exc: Exception) -> LLMError:
    name = type(exc).__name__
    text = str(exc)[:200]
    if "Authentication" in name or "Permission" in name or "Unauthorized" in name:
        return LLMError("auth", text)
    if "RateLimit" in name or "Quota" in name:
        return LLMError("rate", text)
    if "Timeout" in name:
        return LLMError("timeout", text)
    if "Connection" in name or "Network" in name:
        return LLMError("network", text)
    return LLMError("unknown", f"{name}: {text}")
