from __future__ import annotations

import json
import hashlib
import logging
import math
import re
import secrets
import time
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import boto3

from app.core.config import settings
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.store import DynamoStore
from app.services.agent_preferences import preference_command, resolve_tag_ids, tag_label, patch_tag_ids, memory_scope

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_RATIO = 5
SESSION_IDLE_TIMEOUT_MINUTES = 3
DRAFT_LINK_TIMEOUT_MINUTES = 10
UNCATEGORIZED = "\u672a\u6307\u5b9a"
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
LINE_AGENT_PROMPT_PATH = PROMPT_DIR / "line_agent_intent.txt"
logger = logging.getLogger(__name__)
_conversation_id: ContextVar[str | None] = ContextVar("line_agent_conversation_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("line_agent_request_id", default=None)
_line_user_hash: ContextVar[str | None] = ContextVar("line_agent_line_user_hash", default=None)
_app_user_id: ContextVar[str | None] = ContextVar("line_agent_app_user_id", default=None)
_public_base_url: ContextVar[str | None] = ContextVar("line_agent_public_base_url", default=None)


@dataclass
class AgentResult:
    reply: str
    preface: str | None = None
    ticket: dict[str, Any] | None = None
    quick_replies: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


def _hash_line_user_id(line_user_id: str) -> str:
    return hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()[:12]


def _message_log_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {
        "message_length": len(text),
        "message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    if settings.line_agent_log_message_text:
        details["message_text"] = text[:1000]
    return details


def _diagnostic_log(
    event: str,
    *,
    details: dict[str, Any] | None = None,
    intent: str | None = None,
    pending_intent: str | None = None,
    tool: str | None = None,
    duration_ms: int | None = None,
    level: int = logging.INFO,
    exc_info: bool = False,
) -> None:
    if not settings.line_agent_diagnostic_logging:
        return
    logger.log(
        level,
        event,
        exc_info=exc_info,
        extra={
            "event": event,
            "request_id": _request_id.get(),
            "conversation_id": _conversation_id.get(),
            "line_user_hash": _line_user_hash.get(),
            "user_id": _app_user_id.get(),
            "intent": intent,
            "pending_intent": pending_intent,
            "tool": tool,
            "duration_ms": duration_ms,
            "details": details,
        },
    )


def _today() -> date:
    return datetime.now(JST).date()


def _format_yen(amount: int) -> str:
    return f"{amount:,}\u5186"


def _parse_date(text: str) -> tuple[date | None, str | None]:
    today = _today()
    if "\u4e00\u6628\u65e5" in text:
        return today - timedelta(days=2), "\u300c\u4e00\u6628\u65e5\u300d\u304b\u3089\u65e5\u4ed8\u3092\u88dc\u5b8c"
    if "\u6628\u65e5" in text:
        return today - timedelta(days=1), "\u300c\u6628\u65e5\u300d\u304b\u3089\u65e5\u4ed8\u3092\u88dc\u5b8c"
    if "\u4eca\u65e5" in text or "\u672c\u65e5" in text:
        return today, "\u300c\u4eca\u65e5\u300d\u304b\u3089\u65e5\u4ed8\u3092\u88dc\u5b8c"

    match = re.search(r"(?<!\d)(\d{8}|\d{4}[-/]\d{1,2}[-/]\d{1,2})(?!\d)", text)
    if not match:
        return None, None
    raw = match.group(1)
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date(), "\u65e5\u4ed8\u8868\u73fe\u3092\u62bd\u51fa"
        except ValueError:
            continue
    return None, None


def _parse_amount(text: str) -> tuple[int | None, str | None]:
    text = unicodedata.normalize("NFKC", text)
    match = re.search(r"(?<!\d)([0-9,]{2,9})\s*\u5186", text)
    if match:
        return int(match.group(1).replace(",", "")), "\u91d1\u984d\u3092\u300c\u5186\u300d\u8868\u8a18\u304b\u3089\u62bd\u51fa"

    text_without_dates = re.sub(r"(?<!\d)(\d{8}|\d{4}[-/]\d{1,2}[-/]\d{1,2})(?!\d)", " ", text)
    candidates = re.findall(r"(?<!\d)([0-9,]{2,7})(?!\d)", text_without_dates)
    if not candidates:
        return None, None
    return int(candidates[0].replace(",", "")), "\u91d1\u984d\u3089\u3057\u3044\u6570\u5b57\u3092\u62bd\u51fa"


def _has_amount(text: str) -> bool:
    amount, _ = _parse_amount(text)
    return amount is not None


def _category_aliases() -> dict[str, list[str]]:
    return {
        "\u98df\u8cbb": ["\u30b9\u30fc\u30d1\u30fc", "\u30b3\u30f3\u30d3\u30cb", "\u98df\u6750", "\u98df\u54c1", "\u98f2\u6599", "\u3054\u306f\u3093", "\u5f01\u5f53"],
        "\u5916\u98df": ["\u5916\u98df", "\u30e9\u30f3\u30c1", "\u30c7\u30a3\u30ca\u30fc", "\u30ab\u30d5\u30a7", "\u30ec\u30b9\u30c8\u30e9\u30f3", "\u5c45\u9152\u5c4b"],
        "\u65e5\u7528\u54c1": ["\u65e5\u7528\u54c1", "\u6d17\u5264", "\u30c6\u30a3\u30c3\u30b7\u30e5", "\u30c9\u30e9\u30c3\u30b0\u30b9\u30c8\u30a2"],
        "\u5bb6\u8cc3": ["\u5bb6\u8cc3", "\u4f4f\u5b85", "\u4f4f\u5c45"],
        "\u6c34\u9053\u30fb\u5149\u71b1\u8cbb": ["\u96fb\u6c17", "\u30ac\u30b9", "\u6c34\u9053", "\u5149\u71b1\u8cbb"],
        "\u901a\u4fe1\u8cbb": ["\u30b9\u30de\u30db", "\u643a\u5e2f", "\u30cd\u30c3\u30c8", "\u901a\u4fe1", "wifi", "Wi-Fi"],
        "\u4ea4\u901a\u8cbb": ["\u96fb\u8eca", "\u30d0\u30b9", "\u30bf\u30af\u30b7\u30fc", "\u30ac\u30bd\u30ea\u30f3", "\u4ea4\u901a"],
        "\u533b\u7642\u30fb\u5065\u5eb7": ["\u75c5\u9662", "\u85ac", "\u5065\u5eb7", "\u30b8\u30e0"],
        "\u8863\u670d\u30fb\u7f8e\u5bb9": ["\u670d", "\u7f8e\u5bb9", "\u5316\u7ca7", "\u7f8e\u5bb9\u9662"],
        "\u5a2f\u697d\u30fb\u8da3\u5473": ["\u6620\u753b", "\u30b2\u30fc\u30e0", "\u65c5\u884c", "\u30b5\u30d6\u30b9\u30af", "Netflix", "\u5a2f\u697d"],
    }


def _parse_category(text: str, store: DynamoStore) -> tuple[str, str | None]:
    category_names = [row["name"] for row in store.list_categories()]
    for name in category_names:
        if name and name in text:
            return name, "\u767b\u9332\u6e08\u307f\u30ab\u30c6\u30b4\u30ea\u540d\u3092\u62bd\u51fa"

    for category, words in _category_aliases().items():
        if any(word.lower() in text.lower() for word in words):
            if category in category_names:
                return category, f"\u30ad\u30fc\u30ef\u30fc\u30c9\u304b\u3089\u30ab\u30c6\u30b4\u30ea\u300c{category}\u300d\u3092\u63a8\u5b9a"
    return "", None


def _propose_create_category(text: str, ai: dict[str, Any], store: DynamoStore) -> tuple[str, str | None]:
    names = {row["name"] for row in store.list_categories()}
    if re.search(r"カテゴリ(?:は|を)?\s*(?:未指定|なし|無し|空欄)", text):
        return "", "カテゴリ未指定の希望を反映"
    for name in sorted(names, key=len, reverse=True):
        if name and re.search(r"カテゴリ(?:は|を)?\s*[「\"]?" + re.escape(name), text):
            return name, "明示されたカテゴリを反映"
    proposed = _clean_ai_title(ai.get("category"))
    # Creation may infer a category; editing must continue to use only requested changes.
    if proposed and proposed in names:
        return proposed, "Bedrockで登録済みカテゴリから候補を提案"
    category, trace = _parse_category(text, store)
    if category:
        return category, trace
    if "食費" in names and any(word in text for word in ("魚", "カマス", "野菜", "食パン", "牛乳", "お米", "食料品", "サミット")):
        return "食費", "買い物内容から食費を提案"
    return "", None


def _guess_title(text: str, category: str) -> str:
    title = text
    title = re.sub(r"(?<!\d)(\d{8}|\d{4}[-/]\d{1,2}[-/]\d{1,2})(?!\d)", " ", title)
    title = re.sub(r"[0-9,]{2,9}\s*\u5186?", " ", title)
    for word in ["\u5165\u308c\u3068\u3044\u3066", "\u767b\u9332", "\u7cbe\u7b97", "\u6255\u3063\u305f", "\u652f\u6255\u3063\u305f", "\u6628\u65e5", "\u4eca\u65e5", "\u672c\u65e5", "\u4e00\u6628\u65e5"]:
        title = title.replace(word, " ")
    title = " ".join(title.split()).strip("\u3001\u3002 ")
    return (title or category or "LINE\u767b\u9332")[:80]


def _clean_ai_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    title = value.strip().strip("\u300c\u300d\u300e\u300f\"' ")
    title = re.sub(r"\s+", " ", title)
    return title[:80]


def _parse_status(text: str) -> str:
    if "\u53d6\u6d88" in text or "\u53d6\u308a\u6d88\u3057" in text or "\u30ad\u30e3\u30f3\u30bb\u30eb" in text:
        return "canceled"
    if "\u7cbe\u7b97\u6e08" in text or "\u7cbe\u7b97\u6e08\u307f" in text:
        return "settled"
    return "new"


def _user_pair(store: DynamoStore) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    users = {row["email"]: row for row in store.list_users()}
    return users.get("f@example.com"), users.get("o@example.com")


def _other_user(user: dict[str, Any], store: DynamoStore) -> dict[str, Any] | None:
    return next((row for row in store.list_users() if row["id"] != user["id"]), None)


def _parse_payer_user_id(text: str, user: dict[str, Any], store: DynamoStore, ai: dict[str, Any] | None = None) -> tuple[UUID | None, str | None]:
    ai = ai or {}
    payer_name = _clean_ai_title(ai.get("payer") or ai.get("payer_name") or ai.get("payer_user_name"))
    users = store.list_users()
    targets = text
    if payer_name:
        targets = f"{text} {payer_name}"

    for row in users:
        name = row.get("name") or ""
        explicit_payer = name and (
            re.search(rf"(?:立替|立て替え|支払者|payer)\s*(?:は|:)?\s*{re.escape(name)}", text)
            or re.search(rf"{re.escape(name)}\s*(?:が|で)?\s*(?:立替|立て替え|支払|払った)", text)
        )
        if name and (explicit_payer or name == payer_name):
            return UUID(row["id"]), f"立替者を「{name}」として抽出"

    if re.search(r"(?:立替|立て替え|支払|払った|払う|payer)\s*(?:は|:|：)?\s*(?:私|自分|僕|俺|わたし)", targets) or re.search(r"(?:私|自分|僕|俺|わたし)\s*(?:が|で)?\s*(?:立替|立て替え|支払|払った|払う)", targets):
        return UUID(user["id"]), "立替者を送信者本人として抽出"
    if re.search(r"(?:立替|立て替え|支払|払った|払う|payer)\s*(?:は|:|：)?\s*(?:相手|もう一人|パートナー)", targets) or re.search(r"(?:相手|もう一人|パートナー)\s*(?:が|で)?\s*(?:立替|立て替え|支払|払った|払う)", targets):
        other = _other_user(user, store)
        if other:
            return UUID(other["id"]), f"立替者を「{other['name']}」として抽出"
    return None, None


def _parse_ratio_change(text: str, store: DynamoStore, ai: dict[str, Any] | None = None, user: dict[str, Any] | None = None) -> tuple[int | None, int | None, str | None]:
    text = unicodedata.normalize("NFKC", text)
    ai = ai or {}

    def result(first: float, second: float, source: str):
        if first < 0 or second < 0 or first + second <= 0:
            return None, None, None
        f = round(10 * first / (first + second))
        return f, 10 - f, source

    user_f, user_o = _user_pair(store)
    found: dict[str, int] = {}
    for row, key in [(user_f, "f"), (user_o, "o")]:
        if not row:
            continue
        number = "1" if key == "f" else "2"
        names = [row.get("name") or "", f"ユーザ{number}", f"ユーザー{number}", f"User{number}"]
        name = "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True) if n)
        ratio_match = re.search(rf"(?:{name})\s*(?:は|が|:)?\s*(\d{{1,3}})(?!\d)\s*%?(?!円)", text, re.IGNORECASE)
        if ratio_match:
            found[key] = int(ratio_match.group(1))
    if "f" in found and "o" in found:
        f = found["f"]
        o = found["o"]
        return result(f, o, "ユーザー名付きの負担比率を抽出（合計10）")

    if user:
        mine_match = re.search(r"(?:私|自分|僕|俺|わたし)\s*(\d{1,3})\s*[%％]?", text)
        other_match = re.search(r"(?:相手|もう一人|パートナー)\s*(\d{1,3})\s*[%％]?", text)
        if mine_match and other_match:
            mine = int(mine_match.group(1))
            other = int(other_match.group(1))
            user_f, user_o = _user_pair(store)
            if user_f and user["id"] == user_f["id"]:
                return result(mine, other, "送信者と相手の負担比率を抽出")
            if user_o and user["id"] == user_o["id"]:
                return result(other, mine, "送信者と相手の負担比率を抽出")

    # Avoid treating dates (9/20) and times (12:30) as share ratios.
    match = re.search(r"(?<![\d/:-])(\d{1,3})\s*%?\s*[:対]\s*(\d{1,3})\s*%?(?!\d)", text)
    if match and sum(map(int, match.groups())) in (10, 100):
        return result(*map(int, match.groups()), "明示された負担比率を抽出")
    for key_f, key_o in [("ratio_f", "ratio_o"), ("share_ratio_f", "share_ratio_o")]:
        f, o = ai.get(key_f), ai.get(key_o)
        if all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (f, o)):
            if f + o in (10, 100):
                return result(f, o, "Bedrockで負担比率を抽出")
            _diagnostic_log("line_agent_invalid_ratio", details={"ratio_f": f, "ratio_o": o})

    return None, None, None


def _period_month(offset: int = 0) -> tuple[date, date, str]:
    today = _today()
    month = today.month + offset
    year = today.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    first = date(year, month, 1)
    next_month = date(year + (month // 12), (month % 12) + 1, 1)
    return first, next_month - timedelta(days=1), f"{year}\u5e74{month}\u6708"


def _period_year() -> tuple[date, date, str]:
    today = _today()
    return date(today.year, 1, 1), date(today.year, 12, 31), f"{today.year}\u5e74"


def _last_day_of_month(year: int, month: int) -> date:
    next_month = date(year + (month // 12), (month % 12) + 1, 1)
    return next_month - timedelta(days=1)


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_summary_period(text: str, ai: dict[str, Any] | None = None) -> tuple[date, date, str, str]:
    ai = ai or {}
    period = ai.get("period") if isinstance(ai.get("period"), dict) else {}
    ai_from = _parse_iso_date(period.get("from"))
    ai_to = _parse_iso_date(period.get("to"))
    ai_label = _clean_ai_title(period.get("label"))
    if ai_from and ai_to and ai_from <= ai_to:
        label = ai_label or f"{ai_from.isoformat()}\u301c{ai_to.isoformat()}"
        return ai_from, ai_to, label, "Bedrock\u3067\u5bfe\u8c61\u671f\u9593\u3092\u89e3\u91c8"

    month_match = re.search(r"(\d{4})\u5e74\s*(\d{1,2})\u6708", text)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if 1 <= month <= 12:
            return date(year, month, 1), _last_day_of_month(year, month), f"{year}\u5e74{month}\u6708", "\u660e\u793a\u3055\u308c\u305f\u5e74\u6708\u3092\u62bd\u51fa"

    slash_month_match = re.search(r"(?<!\d)(\d{4})[-/](\d{1,2})(?![-/\d])", text)
    if slash_month_match:
        year = int(slash_month_match.group(1))
        month = int(slash_month_match.group(2))
        if 1 <= month <= 12:
            return date(year, month, 1), _last_day_of_month(year, month), f"{year}\u5e74{month}\u6708", "\u660e\u793a\u3055\u308c\u305f\u5e74\u6708\u3092\u62bd\u51fa"

    if any(word in text for word in ["\u5148\u6708", "\u524d\u6708", "\u3053\u306a\u3044\u3060\u306e\u6708"]):
        from_date, to_date, label = _period_month(-1)
        return from_date, to_date, label, "\u5165\u529b\u6587\u304b\u3089\u524d\u6708\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"
    if "\u518d\u6765\u6708" in text:
        from_date, to_date, label = _period_month(2)
        return from_date, to_date, label, "\u5165\u529b\u6587\u304b\u3089\u518d\u6765\u6708\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"
    if "\u6765\u6708" in text:
        from_date, to_date, label = _period_month(1)
        return from_date, to_date, label, "\u5165\u529b\u6587\u304b\u3089\u6765\u6708\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"
    if any(word in text for word in ["\u6628\u5e74", "\u524d\u5e74"]):
        today = _today()
        year = today.year - 1
        return date(year, 1, 1), date(year, 12, 31), f"{year}\u5e74", "\u5165\u529b\u6587\u304b\u3089\u524d\u5e74\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"
    if "\u4eca\u5e74" in text or "\u5e74\u6b21" in text:
        from_date, to_date, label = _period_year()
        return from_date, to_date, label, "\u5165\u529b\u6587\u304b\u3089\u4eca\u5e74\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"

    from_date, to_date, label = _period_month(0)
    return from_date, to_date, label, "\u671f\u9593\u304c\u66d6\u6627\u306a\u305f\u3081\u4eca\u6708\u3092\u5bfe\u8c61\u306b\u8a2d\u5b9a"


def _category_breakdown(tickets: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for ticket in tickets:
        category = ticket.get("category") or UNCATEGORIZED
        totals[category] = totals.get(category, 0) + int(ticket["amount"])
        counts[category] = counts.get(category, 0) + 1
    return sorted(((name, totals[name], counts[name]) for name in totals), key=lambda row: row[1], reverse=True)


def _format_trace(trace: list[str]) -> str:
    # Diagnostics remain in application logs, never in LINE messages.
    return ""


def _tool_log(store: DynamoStore, user: dict[str, Any], tool_name: str, trace: list[str], result: dict[str, Any] | None = None) -> None:
    log_result = result or {}
    store.write_audit(
        "ai_tool_call",
        "ai_agent",
        user["id"],
        None,
        after={
            "conversation_id": _conversation_id.get(),
            "tool": tool_name,
            "trace": trace,
            "result": log_result,
        },
    )
    _diagnostic_log(
        "line_agent_tool_executed",
        tool=tool_name,
        details={"trace": trace, "result": log_result},
    )


def _load_line_agent_prompt() -> str:
    return LINE_AGENT_PROMPT_PATH.read_text(encoding="utf-8")


def _maybe_answer_summary(text: str, user: dict[str, Any], store: DynamoStore, ai: dict[str, Any] | None = None) -> AgentResult | None:
    ai = ai or {}
    wants_summary = ai.get("intent") == "summary" or _is_summary_intent(text)
    if not wants_summary:
        return None

    trace = ["\u8cea\u554f\u610f\u56f3\u3092\u96c6\u8a08\u30fb\u5206\u6790\u3068\u3057\u3066\u5224\u5b9a"]
    from_date, to_date, label, period_trace = _resolve_summary_period(text, ai)
    tag_ids = resolve_tag_ids(text, ai, store) or []
    if len(tag_ids) > 1:
        return AgentResult(reply="集計するタグを1つ指定してください。")
    tag_id = tag_ids[0] if tag_ids else None
    if tag_id:
        if ai.get("all_time") is True or (not ai.get("period") and not re.search(r"今月|先月|前月|今年|去年|昨年|年|月|日", text)):
            from_date, to_date, label = date.min, date.max, "全期間"
        label += f" {tag_label(tag_ids, store)}"
    trace.append(period_trace)
    trace.append(f"\u5bfe\u8c61\u671f\u9593: {label}")

    tickets = store.list_tickets(from_date, to_date, statuses=["new", "settled"], tag_id=tag_id)
    summary = store.summarize(from_date, to_date, ["new", "settled"], tag_id=tag_id)
    breakdown = _category_breakdown(tickets)
    top = breakdown[0] if breakdown else (UNCATEGORIZED, 0, 0)
    trace.extend([
        "search_tickets\u30c4\u30fc\u30eb\u3067\u5bfe\u8c61\u30c1\u30b1\u30c3\u30c8\u3092\u53d6\u5f97",
        "get_summary\u30c4\u30fc\u30eb\u3067\u5408\u8a08\u30fb\u7cbe\u7b97\u984d\u3092\u96c6\u8a08",
        "get_category_breakdown\u30c4\u30fc\u30eb\u3067\u30ab\u30c6\u30b4\u30ea\u5225\u652f\u51fa\u3092\u96c6\u8a08",
    ])

    lines = [
        f"{label}\u306e\u652f\u51fa\u5408\u8a08\u306f{_format_yen(summary['total_amount'])}\u3067\u3059\u3002",
        f"\u30c1\u30b1\u30c3\u30c8\u6570: {summary['ticket_count']}\u4ef6",
        f"\u4e00\u756a\u591a\u3044\u30ab\u30c6\u30b4\u30ea: {top[0]} {_format_yen(top[1])}",
    ]
    settlement = summary["settlement"]
    if settlement["amount"]:
        lines.append(f"\u7cbe\u7b97\u76ee\u5b89: {settlement['from_user']} -> {settlement['to_user']} {_format_yen(settlement['amount'])}")
    else:
        lines.append("\u7cbe\u7b97\u76ee\u5b89: \u7cbe\u7b97\u4e0d\u8981\u3067\u3059\u3002")

    if from_date != date.min and not any(word in text for word in ["\u5148\u6708", "\u524d\u6708"]) and any(word in text for word in ["\u50be\u5411", "\u6bd4\u8f03", "\u6bd4\u3079"]):
        prev_from, prev_to, prev_label = _period_month(-1)
        prev = store.summarize(prev_from, prev_to, ["new", "settled"], tag_id=tag_id)
        diff = summary["total_amount"] - prev["total_amount"]
        sign = "+" if diff >= 0 else "-"
        lines.append(f"{prev_label}\u3068\u306e\u5dee\u5206: {sign}{_format_yen(abs(diff))}")
        trace.append("\u524d\u6708\u30b5\u30de\u30ea\u3092\u53d6\u5f97\u3057\u3066\u5dee\u5206\u3092\u7b97\u51fa")

    _tool_log(store, user, "answer_summary", trace, {"from": from_date.isoformat(), "to": to_date.isoformat()})
    return AgentResult(reply="\n".join(lines) + _format_trace(trace), trace=trace)


def _is_summary_intent(text: str) -> bool:
    words = [
        "\u3044\u304f\u3089",
        "\u5408\u8a08",
        "\u96c6\u8a08",
        "\u50be\u5411",
        "\u591a\u3044",
        "\u4f7f\u3063\u305f",
        "\u4f7f\u3063\u3066\u308b",
        "\u5229\u7528\u91d1\u984d",
        "\u5229\u7528\u984d",
        "\u652f\u51fa",
        "\u51fa\u8cbb",
        "\u91d1\u984d",
        "\u6bd4\u8f03",
        "\u6bd4\u3079",
        "\u5185\u8a33",
        "\u30e9\u30f3\u30ad\u30f3\u30b0",
        "\u30ab\u30c6\u30b4\u30ea",
        "\u6708\u6b21",
        "\u5e74\u6b21",
        "\u7cbe\u7b97",
        "\u7cbe\u7b97\u984d",
        "\u4eca\u6708",
        "\u5148\u6708",
        "\u524d\u6708",
        "\u4eca\u5e74",
        "1\u304b\u6708",
        "1\u30f6\u6708",
        "\uff11\u304b\u6708",
        "\uff11\u30f6\u6708",
        "\u4e00\u304b\u6708",
    ]
    question_words = ["?", "\uff1f", "\u6559\u3048\u3066", "\u3069\u3046", "\u306a\u306b", "\u4f55"]
    return any(word in text for word in words) and (
        any(word in text for word in question_words)
        or any(word in text for word in ["\u50be\u5411", "\u96c6\u8a08", "\u5185\u8a33", "\u30e9\u30f3\u30ad\u30f3\u30b0", "\u6bd4\u8f03", "\u6bd4\u3079", "\u5229\u7528\u91d1\u984d", "\u5229\u7528\u984d", "\u652f\u51fa", "\u7cbe\u7b97", "\u7cbe\u7b97\u984d", "1\u304b\u6708", "1\u30f6\u6708", "\uff11\u304b\u6708", "\uff11\u30f6\u6708"])
    )


def _is_cancel_text(text: str) -> bool:
    return text.strip() in ["\u3084\u3081\u308b", "\u30ad\u30e3\u30f3\u30bb\u30eb", "\u53d6\u308a\u6d88\u3057", "\u4e2d\u6b62", "cancel", "Cancel"]


def _is_confirm_yes(text: str, label: str) -> bool:
    return text.strip() in [label, "OK", "ok", "\u306f\u3044", "\u304a\u9858\u3044"]


def _is_register_intent(text: str, store: DynamoStore) -> bool:
    if _has_amount(text):
        return True
    if any(word in text for word in ["\u767b\u9332", "\u5165\u308c\u3068\u3044\u3066", "\u8a18\u9332", "\u6255\u3063\u305f", "\u652f\u6255\u3063\u305f", "\u4ee3"]):
        return True
    category_names = [row["name"] for row in store.list_categories()]
    return any(name and name in text for name in category_names)


def _is_amount_only_reply(text: str) -> bool:
    stripped = text.strip()
    return re.fullmatch(r"[0-9,]{2,9}\s*(?:\u5186)?(?:\u3067\u3059)?", stripped) is not None


def _pending_key(line_user_id: str) -> str:
    return f"line:{line_user_id}"


def _get_pending(store: DynamoStore, line_user_id: str) -> dict[str, Any] | None:
    row = store._get("AGENT_SESSION", _pending_key(line_user_id))
    if not row:
        return None
    last_active_at = row.get("updated_at") or row.get("created_at")
    if last_active_at:
        try:
            last_active = datetime.fromisoformat(last_active_at)
            if datetime.now(JST) - last_active > timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES):
                store._delete("AGENT_SESSION", _pending_key(line_user_id))
                return None
        except ValueError:
            store._delete("AGENT_SESSION", _pending_key(line_user_id))
            return None
    expires_at = row.get("expires_at")
    if expires_at and expires_at < datetime.now(JST).isoformat():
        store._delete("AGENT_SESSION", _pending_key(line_user_id))
        return None
    return row


def _save_pending(store: DynamoStore, line_user_id: str, payload: dict[str, Any]) -> None:
    now = datetime.now(JST).isoformat()
    expires_at = (datetime.now(JST) + timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)).isoformat()
    existing = store._get("AGENT_SESSION", _pending_key(line_user_id)) or {}
    session = {
        **payload,
        "conversation_id": _conversation_id.get() or existing.get("conversation_id") or str(uuid4()),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "expires_at": expires_at,
    }
    if "draft_token" not in session and existing.get("draft_token"):
        session["draft_token"] = existing["draft_token"]
    store._put("AGENT_SESSION", _pending_key(line_user_id), session)
    _diagnostic_log(
        "line_agent_session_saved",
        pending_intent=str(session.get("intent") or ""),
        details={"expires_at": expires_at, "has_payload": "payload" in session},
    )


def _clear_pending(store: DynamoStore, line_user_id: str, reason: str = "conversation_finished") -> None:
    pending = store._get("AGENT_SESSION", _pending_key(line_user_id))
    draft_token = (pending or {}).get("draft_token")
    if draft_token:
        store._delete("AGENT_DRAFT_LINK", str(draft_token))
    store._delete("AGENT_SESSION", _pending_key(line_user_id))
    _diagnostic_log("line_agent_session_cleared", details={"reason": reason})


def _draft_link_row(store: DynamoStore, token: str) -> dict[str, Any] | None:
    row = store._get("AGENT_DRAFT_LINK", token)
    if not row:
        return None
    try:
        if datetime.now(JST) >= datetime.fromisoformat(str(row["expires_at"])):
            store._delete("AGENT_DRAFT_LINK", token)
            return None
    except (KeyError, ValueError):
        store._delete("AGENT_DRAFT_LINK", token)
        return None
    return row


def _ensure_draft_edit_url(store: DynamoStore, line_user_id: str) -> str | None:
    base_url = _public_base_url.get()
    if not base_url:
        return None
    pending = _get_pending(store, line_user_id)
    if not pending or pending.get("intent") != "confirm_create":
        return None

    token = str(pending.get("draft_token") or "")
    if not token or not _draft_link_row(store, token):
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(JST) + timedelta(minutes=DRAFT_LINK_TIMEOUT_MINUTES)).isoformat()
        store._put(
            "AGENT_DRAFT_LINK",
            token,
            {
                "line_user_id": line_user_id,
                "conversation_id": _conversation_id.get(),
                "expires_at": expires_at,
            },
        )
        session = {
            key: value
            for key, value in pending.items()
            if key not in {"pk", "sk", "entity"}
        }
        session["draft_token"] = token
        store._put("AGENT_SESSION", _pending_key(line_user_id), session)
        _diagnostic_log("line_agent_draft_link_created", details={"expires_at": expires_at})
    return f"{base_url.rstrip('/')}/line/draft/{token}"


def get_ticket_draft_editor(store: DynamoStore, token: str) -> dict[str, Any] | None:
    link = _draft_link_row(store, token)
    if not link:
        return None
    line_user_id = str(link.get("line_user_id") or "")
    _conversation_id.set(str(link.get("conversation_id") or ""))
    _line_user_hash.set(_hash_line_user_id(line_user_id))
    pending = _get_pending(store, line_user_id)
    if not pending or pending.get("intent") != "confirm_create" or not pending.get("payload"):
        return None
    session = {
        key: value
        for key, value in pending.items()
        if key not in {"pk", "sk", "entity", "created_at", "updated_at", "expires_at", "conversation_id"}
    }
    _save_pending(store, line_user_id, session)
    return {
        "payload": pending["payload"],
        "users": store.list_users(),
        "categories": store.list_categories(),
        "tags": store.list_tags(),
        "expires_at": link["expires_at"],
    }


def update_ticket_draft_from_editor(
    store: DynamoStore,
    token: str,
    values: dict[str, Any],
) -> tuple[TicketCreate, dict[str, Any]]:
    editor = get_ticket_draft_editor(store, token)
    if not editor:
        raise ValueError("編集リンクの有効期限が切れています。")
    link = _draft_link_row(store, token)
    if not link:
        raise ValueError("編集リンクの有効期限が切れています。")
    line_user_id = str(link["line_user_id"])
    pending = _get_pending(store, line_user_id)
    if not pending:
        raise ValueError("登録待ちのチケットがありません。")

    before = _ticket_payload_from_dict(pending["payload"])
    users = {str(row["id"]): row for row in editor["users"]}
    categories = {str(row["name"]) for row in editor["categories"]}
    payer_user_id = values.get("payer_user_id", "")
    category = values.get("category", "").strip()
    if payer_user_id not in users:
        raise ValueError("立替者を選択してください。")
    if category and category not in categories:
        raise ValueError("登録済みのカテゴリから選択してください。")

    ratio_f = int(values.get("ratio_f", "5"))
    if not 0 <= ratio_f <= 10:
        raise ValueError("負担比率は0から10の範囲で指定してください。")
    payload = TicketCreate(
        date=datetime.strptime(values.get("date", ""), "%Y-%m-%d").date(),
        title=values.get("title", "").strip(),
        amount=int(values.get("amount", "0")),
        payer_user_id=UUID(payer_user_id),
        ratio_f=ratio_f,
        ratio_o=10 - ratio_f,
        status=values.get("status", "new"),
        category=category,
        memo=values.get("memo", "").strip(),
        tag_ids=values.get("tag_ids", pending["payload"].get("tag_ids", [])),
    )
    before_log = _ticket_payload_log_dict(before)
    known_tags = {row["id"] for row in editor["tags"]}
    if any(str(value) not in known_tags for value in payload.tag_ids):
        raise ValueError("登録済みのタグを選択してください。")
    after_log = _ticket_payload_log_dict(payload)
    changed_fields = [key for key, value in after_log.items() if before_log.get(key) != value]
    trace = [*pending.get("trace", []), "編集フォームで登録候補を更新"]
    _save_pending(
        store,
        line_user_id,
        {
            "intent": "confirm_create",
            "payload": _ticket_payload_dict(payload),
            "trace": trace,
            "draft_token": token,
        },
    )
    _diagnostic_log(
        "line_agent_create_candidate_merged",
        intent="create_ticket",
        pending_intent="confirm_create",
        details={
            "before": before_log,
            "requested_patch": {key: after_log[key] for key in changed_fields},
            "changed_fields": changed_fields,
            "after": after_log,
            "sources": {key: "editor_form" for key in changed_fields},
        },
    )
    return payload, {
        "users": editor["users"],
        "categories": editor["categories"],
        "tags": editor["tags"],
        "line_user_id": line_user_id,
    }


def _ticket_payload_dict(payload: TicketCreate | TicketUpdate) -> dict[str, Any]:
    return {
        "date": payload.date.isoformat(),
        "title": payload.title,
        "amount": payload.amount,
        "payer_user_id": str(payload.payer_user_id),
        "ratio_f": payload.ratio_f,
        "ratio_o": payload.ratio_o,
        "status": payload.status,
        "category": payload.category,
        "memo": payload.memo,
        "tag_ids": [str(value) for value in payload.tag_ids],
    }


def _ticket_payload_log_dict(payload: TicketCreate | TicketUpdate) -> dict[str, Any]:
    logged = _ticket_payload_dict(payload)
    if not settings.line_agent_log_message_text:
        logged.pop("memo", None)
    return logged


def _ticket_payload_from_dict(payload: dict[str, Any]) -> TicketCreate:
    return TicketCreate(
        date=datetime.strptime(payload["date"], "%Y-%m-%d").date(),
        title=payload["title"],
        amount=int(payload["amount"]),
        payer_user_id=UUID(payload["payer_user_id"]),
        ratio_f=int(payload["ratio_f"]),
        ratio_o=int(payload["ratio_o"]),
        status=payload["status"],
        category=payload.get("category") or "",
        memo=payload.get("memo") or "",
        tag_ids=payload.get("tag_ids", []),
    )


def _ticket_update_from_dict(payload: dict[str, Any]) -> TicketUpdate:
    return TicketUpdate(
        date=datetime.strptime(payload["date"], "%Y-%m-%d").date(),
        title=payload["title"],
        amount=int(payload["amount"]),
        payer_user_id=UUID(payload["payer_user_id"]),
        ratio_f=int(payload["ratio_f"]),
        ratio_o=int(payload["ratio_o"]),
        status=payload["status"],
        category=payload.get("category") or "",
        memo=payload.get("memo") or "",
        tag_ids=payload.get("tag_ids", []),
    )


def _parse_title_change(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"(?:\u4ef6\u540d|\u30bf\u30a4\u30c8\u30eb|title)\s*(?:\u306f|\u3092|:|\uff1a)?\s*(.+?)(?:\s*(?:\u306b\u3057\u3066|\u306b\u5909\u66f4|\u3067|\u3002|$))", text, re.IGNORECASE)
    if not match:
        return None, None
    title = _clean_ai_title(match.group(1))
    return (title, "\u4ef6\u540d\u306e\u5909\u66f4\u6307\u793a\u3092\u62bd\u51fa") if title else (None, None)


def _format_create_confirmation(
    payload: TicketCreate,
    user: dict[str, Any],
    store: DynamoStore,
    trace: list[str],
    edit_url: str | None = None,
) -> str:
    payer = store.get_user(payload.payer_user_id)
    payer_name = payer["name"] if payer else user["name"]
    return (
        f"タグ: {tag_label(payload.tag_ids, store)}\n"
        "\u4ee5\u4e0b\u306e\u5185\u5bb9\u3067\u767b\u9332\u3057\u307e\u3059\u304b\uff1f\n"
        f"\u4ef6\u540d: {payload.title}\n"
        f"\u65e5\u4ed8: {payload.date.isoformat()}\n"
        f"\u91d1\u984d: {_format_yen(payload.amount)}\n"
        f"\u30ab\u30c6\u30b4\u30ea: {payload.category or UNCATEGORIZED}\n"
        f"\u7acb\u66ff: {payer_name}\n"
        f"\u8ca0\u62c5\u6bd4\u7387: {payload.ratio_f * 10}% / {payload.ratio_o * 10}%\n\n"
        + (f"項目を画面で修正:\n{edit_url}\n\n" if edit_url else "")
        + "文字で修正する場合は、変更したい項目だけ送ってください。"
        + _format_trace(trace)
    )


def _apply_create_candidate_changes(
    pending_payload: dict[str, Any],
    text: str,
    user: dict[str, Any],
    store: DynamoStore,
    ai: dict[str, Any] | None = None,
) -> tuple[TicketCreate, list[str], bool]:
    ai = ai or {}
    payload = _ticket_payload_from_dict(pending_payload)
    before_payload = _ticket_payload_log_dict(payload)
    changed = False
    sources: dict[str, str] = {}
    trace: list[str] = ["\u767b\u9332\u5019\u88dc\u306b\u5bfe\u3059\u308b\u5909\u66f4\u6307\u793a\u3092\u89e3\u6790"]

    amount_requested = any(word in text for word in ["金額", "価格", "値段", "円"])
    amount, amount_trace = _parse_amount(text) if amount_requested else (None, None)
    amount_source = "rule" if amount else None
    if amount_requested and not amount and isinstance(ai.get("amount"), (int, float)):
        amount = int(ai["amount"])
        amount_trace = "Bedrock\u3067\u91d1\u984d\u5909\u66f4\u3092\u62bd\u51fa"
        amount_source = "bedrock"
    if amount:
        payload.amount = amount
        changed = True
        sources["amount"] = amount_source or "unknown"
        trace.append(amount_trace or "\u91d1\u984d\u5909\u66f4\u3092\u62bd\u51fa")

    date_requested = (
        any(word in text for word in ["日付", "今日", "昨日", "一昨日", "明日"])
        or re.search(r"\d{1,4}[年/-]\d{1,2}(?:[月/-]\d{1,2}日?)?|\d{1,2}日", text) is not None
    )
    parsed_date, date_trace = _parse_date(text) if date_requested else (None, None)
    date_source = "rule" if parsed_date else None
    ai_date = ai.get("date")
    try:
        if date_requested and not parsed_date and ai_date:
            parsed_date = datetime.strptime(str(ai_date), "%Y-%m-%d").date()
            date_trace = "Bedrock\u3067\u65e5\u4ed8\u5909\u66f4\u3092\u88dc\u5b8c"
            date_source = "bedrock"
    except ValueError:
        pass
    if parsed_date:
        payload.date = parsed_date
        changed = True
        sources["date"] = date_source or "unknown"
        trace.append(date_trace or "\u65e5\u4ed8\u5909\u66f4\u3092\u62bd\u51fa")

    category, category_trace = _parse_category(text, store)
    category_source = "rule" if category else None
    ai_category = _clean_ai_title(ai.get("category"))
    category_requested = bool(category) or any(word in text for word in ["カテゴリ", "カテゴリー", "分類", "ジャンル"])
    if not category and ai_category and category_requested:
        category = ai_category
        category_trace = "Bedrock\u3067\u30ab\u30c6\u30b4\u30ea\u5909\u66f4\u3092\u63a8\u5b9a"
        category_source = "bedrock"
    if category:
        payload.category = category
        changed = True
        sources["category"] = category_source or "unknown"
        trace.append(category_trace or "\u30ab\u30c6\u30b4\u30ea\u5909\u66f4\u3092\u62bd\u51fa")

    title, title_trace = _parse_title_change(text)
    title_source = "rule" if title else None
    ai_title = _clean_ai_title(ai.get("title"))
    if not title and ai_title and any(word in text for word in ["\u4ef6\u540d", "\u30bf\u30a4\u30c8\u30eb", "\u540d\u524d"]):
        title = ai_title
        title_trace = "Bedrock\u3067\u4ef6\u540d\u5909\u66f4\u3092\u6574\u5f62"
        title_source = "bedrock"
    if title:
        payload.title = title
        changed = True
        sources["title"] = title_source or "unknown"
        trace.append(title_trace or "\u4ef6\u540d\u5909\u66f4\u3092\u62bd\u51fa")

    payer_requested = any(word in text for word in ["立替", "立て替え", "支払", "払った", "払う", "payer"])
    payer_ai = ai if payer_requested else {}
    payer_user_id, payer_trace = _parse_payer_user_id(text, user, store, payer_ai)
    if payer_user_id:
        payload.payer_user_id = payer_user_id
        changed = True
        sources["payer_user_id"] = (
            "bedrock_assisted"
            if any(payer_ai.get(key) for key in ("payer", "payer_name", "payer_user_name"))
            else "rule"
        )
        trace.append(payer_trace or "立替者変更を抽出")

    explicit_f, explicit_o, _ = _parse_ratio_change(text, store, {}, user)
    ratio_requested = explicit_f is not None or any(word in text for word in ["負担", "比率", "割合", "%", "％", ":", "："])
    ratio_ai = ai if ratio_requested else {}
    ratio_f, ratio_o, ratio_trace = _parse_ratio_change(text, store, ratio_ai, user) if ratio_requested else (None, None, None)
    if ratio_f is not None and ratio_o is not None:
        payload.ratio_f = ratio_f
        payload.ratio_o = ratio_o
        changed = True
        ratio_source = (
            "bedrock"
            if any(ratio_ai.get(key) is not None for key in ("ratio_f", "ratio_o", "share_ratio_f", "share_ratio_o"))
            else "rule"
        )
        sources["ratio_f"] = ratio_source
        sources["ratio_o"] = ratio_source
        trace.append(ratio_trace or "負担比率変更を抽出")

    status = _parse_status(text)
    if status != "new" or "\u672a\u7cbe\u7b97" in text:
        payload.status = status
        changed = True
        sources["status"] = "rule"
        trace.append("\u30b9\u30c6\u30fc\u30bf\u30b9\u5909\u66f4\u3092\u62bd\u51fa")

    if "タグ" in text or "#" in text or "＃" in text:
        tag_ids = patch_tag_ids(payload.tag_ids, text, ai, store)
        payload.tag_ids = [UUID(value) for value in tag_ids]
        sources["tag_ids"] = "explicit_tag_request"
        trace.append("タグ指定を更新")
    after_payload = _ticket_payload_log_dict(payload)
    changed_fields = [
        key for key, value in after_payload.items()
        if before_payload.get(key) != value
    ]
    changed = bool(changed_fields)
    requested_patch = {key: after_payload[key] for key in changed_fields}
    _diagnostic_log(
        "line_agent_create_candidate_merged",
        intent=str(ai.get("intent") or "create_ticket"),
        pending_intent="confirm_create",
        details={
            **_message_log_details(text),
            "before": before_payload,
            "bedrock_extraction": ai,
            "requested_patch": requested_patch,
            "changed_fields": changed_fields,
            "after": after_payload,
            "sources": {key: sources.get(key, "unknown") for key in changed_fields},
        },
    )
    return payload, trace, changed


def _confirm_create(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    if not pending or pending.get("intent") != "confirm_create":
        return _create_ticket_candidate(text, user, store, line_user_id, ai)

    if _is_confirm_yes(text, "\u767b\u9332\u3059\u308b"):
        try:
            payload = _ticket_payload_from_dict(pending["payload"])
            ticket = store.create_ticket(payload, UUID(user["id"]))
        except ValueError as exc:
            return AgentResult(reply=f"{exc}\n候補を修正するか、やめると送ってください。")
        store.write_audit("ticket_create", "ticket", user["id"], ticket["id"], after=store.ticket_audit_dict(ticket))
        _clear_pending(store, line_user_id, reason="ticket_created")
        trace = [*pending.get("trace", []), "create_ticket\u30c4\u30fc\u30eb\u3092\u5b9f\u884c", "\u767b\u9332\u7d50\u679c\u3092\u78ba\u8a8d"]
        _tool_log(store, user, "create_ticket", trace, {"ticket_id": ticket["id"], "display_id": ticket.get("display_id")})
        reply = (
            "\u767b\u9332\u3057\u307e\u3057\u305f\u3002\n"
            f"\u30c1\u30b1\u30c3\u30c8ID: {ticket.get('display_id') or '-'}\n"
            f"\u4ef6\u540d: {ticket['title']}\n"
            f"\u65e5\u4ed8: {ticket['date']}\n"
            f"\u91d1\u984d: {_format_yen(ticket['amount'])}\n"
            f"\u30ab\u30c6\u30b4\u30ea: {ticket.get('category') or UNCATEGORIZED}\n"
            f"\u7acb\u66ff: {ticket.get('payer_name') or user['name']}"
        )
        return AgentResult(reply=reply + _format_trace(trace), ticket=ticket, trace=trace)

    if _is_cancel_text(text):
        _clear_pending(store, line_user_id, reason="ticket_create_canceled")
        return AgentResult(reply="\u767b\u9332\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    payload, change_trace, changed = _apply_create_candidate_changes(pending["payload"], text, user, store, ai)
    if changed:
        trace = [*pending.get("trace", []), *change_trace, "\u767b\u9332\u524d\u78ba\u8a8d\u3092\u66f4\u65b0"]
        _save_pending(store, line_user_id, {"intent": "confirm_create", "payload": _ticket_payload_dict(payload), "trace": trace})
        edit_url = _ensure_draft_edit_url(store, line_user_id)
        return AgentResult(
            reply="\u767b\u9332\u5019\u88dc\u3092\u4fee\u6b63\u3057\u307e\u3057\u305f\u3002\n" + _format_create_confirmation(payload, user, store, trace, edit_url),
            quick_replies=["\u767b\u9332\u3059\u308b", "\u3084\u3081\u308b"],
            trace=trace,
        )

    return AgentResult(
        reply=(
            "\u767b\u9332\u5f85\u3061\u306e\u5019\u88dc\u304c\u3042\u308a\u307e\u3059\u3002\n"
            "\u767b\u9332\u3059\u308b\u5834\u5408\u306f\u300c\u767b\u9332\u3059\u308b\u300d\u3001\u4fee\u6b63\u3059\u308b\u5834\u5408\u306f\u300c\u91d1\u984d\u30924321\u5186\u306b\u3057\u3066\u300d\u306e\u3088\u3046\u306b\u9001\u3063\u3066\u304f\u3060\u3055\u3044\u3002"
        ),
        quick_replies=["\u767b\u9332\u3059\u308b", "\u3084\u3081\u308b"],
    )


def _create_ticket_candidate(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    is_new_request = pending is None
    base_text = f"{pending.get('text', '')} {text}" if pending and pending.get("intent") == "create_ticket" else text
    trace: list[str] = ["\u5165\u529b\u6587\u3092\u30c1\u30b1\u30c3\u30c8\u4f5c\u6210\u5019\u88dc\u3068\u3057\u3066\u89e3\u6790"]
    ai = ai or {}
    friendly_comment = _clean_ai_title(ai.get("friendly_comment")) if is_new_request else ""

    amount, amount_trace = _parse_amount(base_text)
    parsed_date, date_trace = _parse_date(base_text)
    category, category_trace = _propose_create_category(base_text, ai, store)
    status = _parse_status(base_text)
    ai_title = _clean_ai_title(ai.get("title"))
    ai_amount = ai.get("amount")
    ai_date = ai.get("date")
    if isinstance(ai_amount, (int, float)) and not amount:
        amount = int(ai_amount)
        amount_trace = "Bedrock\u3067\u91d1\u984d\u3092\u62bd\u51fa"
    if isinstance(ai.get("status"), str) and ai["status"] in ["new", "settled", "canceled"]:
        status = ai["status"]
    payer_user_id, payer_trace = _parse_payer_user_id(base_text, user, store, ai)
    ratio_f, ratio_o, ratio_trace = _parse_ratio_change(base_text, store, ai, user)
    if ratio_f is None and any(ai.get(key) is not None for key in ("ratio_f", "ratio_o", "share_ratio_f", "share_ratio_o")):
        _save_pending(store, line_user_id, {"intent": "create_ticket", "text": base_text})
        return AgentResult(reply="負担比率を正しく読み取れませんでした。『ユーザー1 3、ユーザー2 7』のように合計10で教えてね。まだ登録していません。")
    try:
        if ai_date and not parsed_date:
            parsed_date = datetime.strptime(str(ai_date), "%Y-%m-%d").date()
            date_trace = "Bedrock\u3067\u65e5\u4ed8\u3092\u88dc\u5b8c"
    except ValueError:
        pass
    if amount_trace:
        trace.append(amount_trace)
    if date_trace:
        trace.append(date_trace)
    if category_trace:
        trace.append(category_trace)
    if payer_trace:
        trace.append(payer_trace)
    if ratio_trace:
        trace.append(ratio_trace)
    date_defaulted = parsed_date is None
    if not parsed_date:
        parsed_date = _today()
        trace.append("\u65e5\u4ed8\u6307\u5b9a\u304c\u306a\u3044\u305f\u3081\u4eca\u65e5\u306e\u65e5\u4ed8\u3092\u4f7f\u7528")

    if not amount:
        _save_pending(store, line_user_id, {"intent": "create_ticket", "text": base_text})
        trace.append("\u91d1\u984d\u304c\u4e0d\u8db3\u3057\u3066\u3044\u308b\u305f\u3081\u805e\u304d\u8fd4\u3057")
        _tool_log(store, user, "ask_missing_amount", trace)
        return AgentResult(
            reply=(
                "\u30c1\u30b1\u30c3\u30c8\u767b\u9332\u306e\u9014\u4e2d\u3067\u3059\u304c\u3001\u91d1\u984d\u304c\u5206\u304b\u308a\u307e\u305b\u3093\u3002\n"
                "\u7d9a\u3051\u308b\u5834\u5408\u306f\u300c3200\u5186\u300d\u306e\u3088\u3046\u306b\u91d1\u984d\u3092\u9001\u3063\u3066\u304f\u3060\u3055\u3044\u3002\n"
                "\u3084\u3081\u308b\u5834\u5408\u306f\u300c\u3084\u3081\u308b\u300d\u3068\u9001\u3063\u3066\u304f\u3060\u3055\u3044\u3002"
                + _format_trace(trace)
            ),
            preface=friendly_comment or "了解！登録内容を一緒に確認するね。",
            trace=trace,
        )

    title = ai_title or _guess_title(base_text, category)
    payload = TicketCreate(
        date=parsed_date,
        title=title,
        amount=amount,
        payer_user_id=payer_user_id or UUID(user["id"]),
        ratio_f=ratio_f if ratio_f is not None else DEFAULT_RATIO,
        ratio_o=ratio_o if ratio_o is not None else DEFAULT_RATIO,
        status=status,
        category=category,
        memo=f"LINE\u304b\u3089\u767b\u9332: {base_text.strip()}",
        tag_ids=resolve_tag_ids(base_text, ai, store) or [],
    )
    _diagnostic_log(
        "line_agent_create_candidate_created",
        intent=str(ai.get("intent") or "create_ticket"),
        details={
            **_message_log_details(base_text),
            "bedrock_extraction": ai,
            "candidate": _ticket_payload_log_dict(payload),
            "defaults_applied": {
                "date": date_defaulted,
                "payer_user_id": payer_user_id is None,
                "ratio": ratio_f is None or ratio_o is None,
            },
            "trace": trace,
        },
    )
    _save_pending(store, line_user_id, {"intent": "confirm_create", "payload": _ticket_payload_dict(payload), "trace": trace})
    trace.append("\u767b\u9332\u524d\u78ba\u8a8d\u3092\u4f5c\u6210")
    edit_url = _ensure_draft_edit_url(store, line_user_id)
    reply = _format_create_confirmation(payload, user, store, trace, edit_url)
    return AgentResult(
        reply=reply,
        preface=friendly_comment or f"了解！{title}の内容を確認するね。",
        quick_replies=["\u767b\u9332\u3059\u308b", "\u3084\u3081\u308b"],
        trace=trace,
    )


def _find_ticket_by_display_id(store: DynamoStore, display_id: int) -> dict[str, Any] | None:
    return next((ticket for ticket in store.list_tickets(statuses=["new", "settled", "canceled"]) if ticket.get("display_id") == display_id), None)


def _ticket_line(ticket: dict[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    return (
        f"{prefix}{ticket.get('date')} "
        f"{ticket.get('title')} "
        f"{_format_yen(int(ticket.get('amount', 0)))} "
        f"/ {ticket.get('category') or UNCATEGORIZED} "
        f"/ 立替: {ticket.get('payer_name') or '-'}"
    )


def _parse_candidate_choice(text: str) -> int | None:
    match = re.search(r"(?:削除|選択|候補)?\s*([1-5１-５])", text)
    if not match:
        return None
    raw = match.group(1)
    return "１２３４５".find(raw) + 1 if raw in "１２３４５" else int(raw)


def _ticket_search_terms(text: str, ai: dict[str, Any] | None = None) -> dict[str, Any]:
    ai = ai or {}
    amount, _ = _parse_amount(text)
    parsed_date, _ = _parse_date(text)
    title = _clean_ai_title(ai.get("title"))
    category = _clean_ai_title(ai.get("category"))
    ai_amount = ai.get("amount")
    ai_date = _parse_iso_date(ai.get("date"))
    fallback_title = _guess_title(text, category)
    for word in ["削除", "消して", "消す", "取り消し", "取り消して", "なかったこと", "変更", "修正", "更新", "直して", "直す"]:
        fallback_title = fallback_title.replace(word, " ")
    fallback_title = " ".join(fallback_title.split())
    return {
        "title": title or fallback_title,
        "amount": amount or (int(ai_amount) if isinstance(ai_amount, (int, float)) else None),
        "date": parsed_date or ai_date,
        "category": category,
    }


def _find_ticket_candidates(text: str, user: dict[str, Any], store: DynamoStore, ai: dict[str, Any] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    terms = _ticket_search_terms(text, ai)
    rows = store.list_tickets(statuses=["new", "settled", "canceled"])
    scored: list[tuple[int, str, dict[str, Any]]] = []
    title_terms = [word for word in re.split(r"\s+", terms["title"]) if len(word) >= 2]
    for ticket in rows:
        score = 0
        if terms["date"] and ticket.get("date") == terms["date"].isoformat():
            score += 40
        if terms["amount"] and int(ticket.get("amount", 0)) == terms["amount"]:
            score += 35
        if terms["category"] and terms["category"] == (ticket.get("category") or ""):
            score += 25
        ticket_title = ticket.get("title") or ""
        for term in title_terms:
            if term and term in ticket_title:
                score += 20
        if ticket.get("created_by") == user["id"] or ticket.get("payer_user_id") == user["id"]:
            score += 5
        if score > 0:
            scored.append((score, ticket.get("updated_at", ""), ticket))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in scored[:limit]]


def _recent_ticket_candidates(store: DynamoStore, user: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    rows = [
        row for row in store.list_tickets(statuses=["new", "settled", "canceled"])
        if row.get("created_by") == user["id"] or row.get("payer_user_id") == user["id"]
    ]
    rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    return rows[:limit]


def _parse_display_id(text: str) -> int | None:
    match = re.search(r"(?:\u30c1\u30b1\u30c3\u30c8ID|ID|#)\s*[:\uff1a]?\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_delete_intent(text: str) -> bool:
    return any(word in text for word in ["\u524a\u9664", "\u6d88\u3057\u3066", "\u53d6\u308a\u6d88\u3057", "\u6d88\u3059", "\u306a\u304b\u3063\u305f\u3053\u3068"])


def _is_update_intent(text: str) -> bool:
    return any(word in text for word in ["\u5909\u66f4", "\u4fee\u6b63", "\u76f4\u3057\u3066", "\u66f4\u65b0", "\u76f4\u3059"]) and (_parse_display_id(text) is not None or _is_recent_reference(text))


def _is_recent_reference(text: str) -> bool:
    return any(word in text for word in ["\u3055\u3063\u304d", "\u76f4\u8fd1", "\u6700\u5f8c", "\u4eca\u767b\u9332\u3057\u305f", "\u524d\u306e"])


def _recent_ticket(store: DynamoStore, user: dict[str, Any]) -> dict[str, Any] | None:
    rows = [
        row for row in store._items("TICKET")
        if not row.get("deleted_at") and (row.get("created_by") == user["id"] or row.get("payer_user_id") == user["id"])
    ]
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return store.with_payer_name(rows[0]) if rows else None


def _handle_delete(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, target_ticket: dict[str, Any] | None = None, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    if pending and pending.get("intent") == "select_delete_candidate":
        choice = _parse_candidate_choice(text)
        candidates = pending.get("candidates") or []
        if choice and 1 <= choice <= len(candidates):
            ticket = store.get_ticket(candidates[choice - 1])
            if not ticket:
                _clear_pending(store, line_user_id)
                return AgentResult(reply="対象チケットが見つかりませんでした。もう一度指定してください。")
            ticket = store.with_payer_name(ticket)
            trace = [*pending.get("trace", []), f"削除候補 {choice} を選択"]
            _save_pending(store, line_user_id, {"intent": "confirm_delete", "ticket_id": ticket["id"], "trace": trace})
            reply = (
                "このチケットを削除しますか？\n"
                f"{_ticket_line(ticket)}"
            )
            return AgentResult(reply=reply + _format_trace(trace), quick_replies=["削除する", "やめる"], trace=trace)
        if _is_cancel_text(text):
            _clear_pending(store, line_user_id)
            return AgentResult(reply="削除を取り消しました。")
        lines = ["削除するチケットを番号で選んでください。"]
        for index, ticket_id in enumerate(candidates, start=1):
            ticket = store.get_ticket(ticket_id)
            if ticket:
                lines.append(_ticket_line(store.with_payer_name(ticket), index))
        return AgentResult(reply="\n".join(lines), quick_replies=[f"削除 {i}" for i in range(1, len(candidates) + 1)] + ["やめる"])

    if pending and pending.get("intent") == "confirm_delete":
        ticket_id = pending["ticket_id"]
        if _is_confirm_yes(text, "\u524a\u9664\u3059\u308b"):
            try:
                before, after = store.delete_ticket(UUID(ticket_id), UUID(user["id"]))
            except KeyError:
                _clear_pending(store, line_user_id)
                return AgentResult(reply="\u5bfe\u8c61\u30c1\u30b1\u30c3\u30c8\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002")
            store.write_audit("ticket_delete", "ticket", user["id"], ticket_id, before=before, after=after)
            _clear_pending(store, line_user_id)
            trace = [*pending.get("trace", []), "delete_ticket\u30c4\u30fc\u30eb\u3092\u5b9f\u884c"]
            _tool_log(store, user, "delete_ticket", trace, {"ticket_id": ticket_id})
            return AgentResult(reply="\u30c1\u30b1\u30c3\u30c8\u3092\u524a\u9664\u3057\u307e\u3057\u305f\u3002" + _format_trace(trace), trace=trace)
        if _is_cancel_text(text):
            _clear_pending(store, line_user_id)
            return AgentResult(reply="\u524a\u9664\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    display_id = _parse_display_id(text)
    ticket = target_ticket or (_find_ticket_by_display_id(store, display_id) if display_id is not None else None)
    if not ticket and _is_recent_reference(text):
        ticket = _recent_ticket(store, user)
    if not ticket:
        candidates = _find_ticket_candidates(text, user, store, ai)
        if not candidates and any(word in text for word in ["どれ", "一覧", "候補", "チケット", "削除"]):
            candidates = _recent_ticket_candidates(store, user)
        if len(candidates) == 1:
            ticket = candidates[0]
        elif len(candidates) > 1:
            trace = ["delete_ticketツールの対象候補を検索", f"{len(candidates)}件の候補を提示"]
            _save_pending(store, line_user_id, {"intent": "select_delete_candidate", "candidates": [row["id"] for row in candidates], "trace": trace})
            lines = ["削除候補が複数あります。どれを削除しますか？"]
            for index, row in enumerate(candidates, start=1):
                lines.append(_ticket_line(row, index))
            return AgentResult(reply="\n".join(lines) + _format_trace(trace), quick_replies=[f"削除 {i}" for i in range(1, len(candidates) + 1)] + ["やめる"], trace=trace)
    if not ticket:
        candidates = _recent_ticket_candidates(store, user)
        if candidates:
            trace = ["delete_ticketツールの対象を特定できないため直近候補を提示"]
            _save_pending(store, line_user_id, {"intent": "select_delete_candidate", "candidates": [row["id"] for row in candidates], "trace": trace})
            lines = ["削除対象を特定できませんでした。近い候補から選んでください。"]
            for index, row in enumerate(candidates, start=1):
                lines.append(_ticket_line(row, index))
            return AgentResult(reply="\n".join(lines) + _format_trace(trace), quick_replies=[f"削除 {i}" for i in range(1, len(candidates) + 1)] + ["やめる"], trace=trace)
        return AgentResult(reply="削除対象のチケットが見つかりませんでした。件名、日付、金額などを含めてもう一度指定してください。")
    trace = ["delete_ticket\u30c4\u30fc\u30eb\u306e\u5b9f\u884c\u524d\u78ba\u8a8d\u3092\u4f5c\u6210"]
    _save_pending(store, line_user_id, {"intent": "confirm_delete", "ticket_id": ticket["id"], "trace": trace})
    reply = (
        "\u3053\u306e\u30c1\u30b1\u30c3\u30c8\u3092\u524a\u9664\u3057\u307e\u3059\u304b\uff1f\n"
        f"\u30c1\u30b1\u30c3\u30c8ID: {ticket.get('display_id')}\n"
        f"\u4ef6\u540d: {ticket['title']}\n"
        f"\u65e5\u4ed8: {ticket['date']}\n"
        f"\u91d1\u984d: {_format_yen(ticket['amount'])}"
    )
    return AgentResult(reply=reply + _format_trace(trace), quick_replies=["\u524a\u9664\u3059\u308b", "\u3084\u3081\u308b"], trace=trace)


def _handle_update(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, target_ticket: dict[str, Any] | None = None, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    if pending and pending.get("intent") == "select_update_candidate":
        choice = re.fullmatch(r"(?:選択\s*)?([1-5１-５])(?:番)?", text.strip())
        if not choice:
            return AgentResult(reply="候補の番号を選んでください。検索をやり直す場合は「やめる」と送ってください。", quick_replies=[f"選択 {i + 1}" for i in range(len(pending["candidate_ids"]))] + ["やめる"])
        index = int(choice.group(1)) - 1
        ids = pending["candidate_ids"]
        if index >= len(ids):
            return AgentResult(reply="表示された候補の番号を選んでください。")
        ticket = store.get_ticket(UUID(ids[index]))
        if not ticket:
            _clear_pending(store, line_user_id)
            return AgentResult(reply="そのチケットは削除されています。もう一度検索してください。")
        _save_pending(store, line_user_id, {"intent": "edit_update", "ticket_id": ticket["id"], "payload": _ticket_payload_dict(_ticket_payload_from_dict(ticket))})
        return AgentResult(reply=f"{_ticket_line(ticket)}\nどの項目をどう変更しますか？例：金額を1800円にして。", quick_replies=["やめる"])
    if pending and pending.get("intent") in {"edit_update", "confirm_update"}:
        target_ticket = store.get_ticket(UUID(pending["ticket_id"]))
        if not target_ticket:
            _clear_pending(store, line_user_id)
            return AgentResult(reply="対象のチケットは削除されています。")
        target_ticket = {**target_ticket, **pending["payload"]}
    if pending and pending.get("intent") == "confirm_update":
        ticket_id = pending["ticket_id"]
        if _is_confirm_yes(text, "\u66f4\u65b0\u3059\u308b"):
            try:
                before, ticket = store.update_ticket(UUID(ticket_id), _ticket_update_from_dict(pending["payload"]), UUID(user["id"]))
            except ValueError as exc:
                return AgentResult(reply=f"{exc}\n候補を修正するか、やめると送ってください。")
            except KeyError:
                _clear_pending(store, line_user_id)
                return AgentResult(reply="\u5bfe\u8c61\u30c1\u30b1\u30c3\u30c8\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002")
            store.write_audit("ticket_update", "ticket", user["id"], ticket_id, before=before, after=store.ticket_audit_dict(ticket))
            _clear_pending(store, line_user_id)
            trace = [*pending.get("trace", []), "update_ticket\u30c4\u30fc\u30eb\u3092\u5b9f\u884c"]
            _tool_log(store, user, "update_ticket", trace, {"ticket_id": ticket_id, "display_id": ticket.get("display_id")})
            return AgentResult(reply="\u30c1\u30b1\u30c3\u30c8\u3092\u66f4\u65b0\u3057\u307e\u3057\u305f\u3002" + _format_trace(trace), ticket=ticket, trace=trace)
        if _is_cancel_text(text):
            _clear_pending(store, line_user_id)
            return AgentResult(reply="\u66f4\u65b0\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    display_id = _parse_display_id(text)
    ticket = target_ticket or (_find_ticket_by_display_id(store, display_id) if display_id is not None else None)
    if not ticket and _is_recent_reference(text):
        ticket = _recent_ticket(store, user)
    if not ticket:
        target = (ai or {}).get("target")
        target = target if isinstance(target, dict) else {}
        title = str(target.get("title") or (ai or {}).get("title") or "").strip()
        target_date = _parse_iso_date(target.get("date")) or _parse_date(text)[0]
        rows = store.list_tickets(statuses=["new", "settled", "canceled"])
        if target_date:
            rows = [r for r in rows if r["date"] == target_date.isoformat()]
        if title:
            rows = [r for r in rows if title.casefold() in r["title"].casefold()]
        rows = rows[:5]
        if not rows:
            return AgentResult(reply="条件に合うチケットが見つかりませんでした。件名の一部や日付を変えて教えてください。")
        _save_pending(store, line_user_id, {"intent": "select_update_candidate", "candidate_ids": [r["id"] for r in rows]})
        return AgentResult(reply="変更するチケットを選んでください。\n" + "\n".join(_ticket_line(r, i + 1) for i, r in enumerate(rows)), quick_replies=[f"選択 {i + 1}" for i in range(len(rows))] + ["やめる"])

    # Reuse the explicit field patch gate: attaching a tag must not change money or shares.
    candidate, changes, changed = _apply_create_candidate_changes(ticket, text, user, store, ai)
    if not changed:
        _save_pending(store, line_user_id, {"intent": "edit_update", "ticket_id": ticket["id"], "payload": _ticket_payload_dict(candidate)})
        return AgentResult(reply=f"{_ticket_line(ticket)}\n変更したい項目と値を教えてください。まだ更新していません。", quick_replies=["やめる"])
    payload = _ticket_update_from_dict(_ticket_payload_dict(candidate))
    trace = ["update_ticket\u30c4\u30fc\u30eb\u306e\u5b9f\u884c\u524d\u78ba\u8a8d\u3092\u4f5c\u6210"]
    trace.extend(changes)
    _save_pending(store, line_user_id, {"intent": "confirm_update", "ticket_id": ticket["id"], "payload": _ticket_payload_dict(payload), "trace": trace})
    reply = (
        "\u3053\u306e\u5185\u5bb9\u306b\u66f4\u65b0\u3057\u307e\u3059\u304b\uff1f\n"
        f"\u30c1\u30b1\u30c3\u30c8ID: {ticket.get('display_id')}\n"
        f"\u4ef6\u540d: {payload.title}\n"
        f"\u65e5\u4ed8: {payload.date.isoformat()}\n"
        f"\u91d1\u984d: {_format_yen(payload.amount)}\n"
        f"\u30ab\u30c6\u30b4\u30ea: {payload.category or UNCATEGORIZED}\n"
        f"\u30b9\u30c6\u30fc\u30bf\u30b9: {payload.status}"
    )
    return AgentResult(reply=reply + f"\nタグ: {tag_label(payload.tag_ids, store)}" + _format_trace(trace), quick_replies=["\u66f4\u65b0\u3059\u308b", "\u3084\u3081\u308b"], trace=trace)


def _try_bedrock_intent(text: str, categories: list[str], memories: list | None = None, tags: list | None = None, pending: dict | None = None, *, proposal_only: bool = False) -> dict[str, Any] | None:
    if settings.line_agent_mode != "bedrock":
        _diagnostic_log("bedrock_intent_skipped", details={"reason": "line_agent_mode_is_not_bedrock"})
        return None
    started_at = time.perf_counter()
    try:
        _diagnostic_log(
            "bedrock_intent_started",
            details={
                **_message_log_details(text),
                "model_id": settings.bedrock_model_id,
                "category_count": len(categories),
            },
        )
        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        prompt = json.dumps({
            "input": text, "today": _today().isoformat(), "categories": categories,
            "task": "新規登録の候補を補完。intent=create_ticketとし、購入物を短く要約したtitle、話題に触れるfriendly_comment、妥当なcategoryを必ず検討。他の数値や日付は再解釈しない。" if proposal_only else "意図と項目を解析",
            "saved_preferences": [{"id": r["id"], "content": r["content"], "scope": r.get("scope", "personal")} for r in (memories or [])],
            "tags": [{"name": r["name"]} for r in (tags or [])],
            "current_operation": {k: pending[k] for k in ("intent", "payload", "text") if k in pending} if pending else None,
        }, ensure_ascii=False)
        response = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": _load_line_agent_prompt()}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 2048, "temperature": 0},
        )
        if response.get("stopReason") == "max_tokens":
            raise ValueError("Bedrock intent output was truncated")
        content = "".join(block["text"] for block in response["output"]["message"]["content"] if "text" in block)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        if not isinstance(parsed, dict):
            raise ValueError("Bedrock intent output must be an object")
        _diagnostic_log(
            "bedrock_intent_completed",
            intent=str(parsed.get("intent") or ""),
            duration_ms=round((time.perf_counter() - started_at) * 1000),
            details={
                "model_id": settings.bedrock_model_id,
                "parsed": {k: v for k, v in parsed.items() if k != "memory_content"},
                "usage": response.get("usage") or {},
                "stop_reason": response.get("stopReason"),
                **({"raw_output": content[:2000]} if settings.line_agent_log_message_text else {}),
            },
        )
        return parsed
    except Exception:
        _diagnostic_log(
            "bedrock_intent_failed",
            duration_ms=round((time.perf_counter() - started_at) * 1000),
            details={"model_id": settings.bedrock_model_id},
            level=logging.ERROR,
            exc_info=True,
        )
        return None


def _ticket_from_ai_target(ai: dict[str, Any], user: dict[str, Any], store: DynamoStore) -> dict[str, Any] | None:
    target_display_id = ai.get("target_display_id")
    if isinstance(target_display_id, (int, float)):
        ticket = _find_ticket_by_display_id(store, int(target_display_id))
        if ticket:
            return ticket
    if ai.get("target_reference") == "recent":
        return _recent_ticket(store, user)
    return None


def _unknown_reply(ai: dict[str, Any] | None = None) -> AgentResult:
    friendly_comment = _clean_ai_title((ai or {}).get("friendly_comment"))
    if friendly_comment:
        return AgentResult(reply=friendly_comment)
    if (ai or {}).get("intent") == "chat":
        return AgentResult(reply="うんうん、いいね！もう少し聞かせて。")
    reason = _clean_ai_title((ai or {}).get("reason"))
    if reason:
        return AgentResult(reply=f"\u305d\u306e\u4f9d\u983c\u306f\u5bb6\u8a08\u7c3f\u64cd\u4f5c\u3068\u3057\u3066\u306f\u5bfe\u5fdc\u3067\u304d\u307e\u305b\u3093\u3002\n\u7406\u7531: {reason}")
    return AgentResult(
        reply=(
            "\u3084\u308a\u305f\u3044\u64cd\u4f5c\u3092\u8aad\u307f\u53d6\u308c\u307e\u305b\u3093\u3067\u3057\u305f\u3002\n"
            "\u4f8b:\n"
            "\u6628\u65e5\u30b9\u30fc\u30d1\u30fc\u30673200\u5186\n"
            "\u524d\u6708\u306e\u7cbe\u7b97\u984d\u3092\u6559\u3048\u3066\n"
            "\u30c1\u30b1\u30c3\u30c8ID 10 \u91d1\u984d 3500\u5186\u306b\u5909\u66f4\n"
            "\u30c1\u30b1\u30c3\u30c8ID 10 \u524a\u9664"
        )
    )


def handle_line_text(
    text: str,
    line_user_id: str,
    user: dict[str, Any],
    store: DynamoStore,
    request_id: str | None = None,
    public_base_url: str | None = None,
) -> AgentResult:
    text = unicodedata.normalize("NFKC", text)
    pending = _get_pending(store, line_user_id)
    conversation_id = str((pending or {}).get("conversation_id") or uuid4())
    _conversation_id.set(conversation_id)
    _request_id.set(request_id)
    _line_user_hash.set(_hash_line_user_id(line_user_id))
    _app_user_id.set(str(user.get("id") or ""))
    _public_base_url.set(public_base_url)
    _diagnostic_log(
        "line_agent_message_started",
        pending_intent=str((pending or {}).get("intent") or ""),
        details={
            **_message_log_details(text),
            "agent_mode": settings.line_agent_mode,
            "has_pending_session": pending is not None,
        },
    )
    if _is_cancel_text(text):
        _clear_pending(store, line_user_id, reason="user_canceled")
        return AgentResult(reply="\u9032\u884c\u4e2d\u306e\u64cd\u4f5c\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    if pending and pending.get("intent") == "confirm_memory":
        if text.strip() == "この方針を保存":
            try:
                scope_text = "共通で覚えて" if pending.get("scope") == "shared" else "覚えて"
                reply = preference_command(scope_text, {"intent": "remember", "memory_content": pending["content"]}, user, store)
            except ValueError as exc:
                return AgentResult(reply=str(exc))
        elif text.strip() == "保存しない":
            reply = "注意事項は保存していません。"
        else:
            return AgentResult(reply="この方針を今後も使うか選んでください。", quick_replies=["この方針を保存", "保存しない"])
        resume = pending.get("resume")
        if resume:
            _save_pending(store, line_user_id, resume)
        else:
            _clear_pending(store, line_user_id)
        return AgentResult(reply=reply or "保存できませんでした。")

    if pending and pending.get("intent") == "select_update_candidate":
        return _handle_update(text, user, store, line_user_id)
    categories = [row["name"] for row in store.list_categories()]
    if pending and pending.get("intent") == "confirm_create" and _is_confirm_yes(text, "登録する"):
        return _confirm_create(text, user, store, line_user_id)
    memories = [*store.list_memories(str(user["id"]), "shared"), *store.list_memories(str(user["id"]))]
    bedrock_intent = _try_bedrock_intent(text, categories, memories, store.list_tags(), pending)
    if bedrock_intent is None and settings.line_agent_mode == "bedrock":
        return AgentResult(reply="ごめんね、今はAIの読み取りに失敗しました。内容は登録・変更していません。少し待ってもう一度送ってね。")
    # Recover short expense inputs rejected as chat, without hijacking explicit operations.
    if (bedrock_intent or {}).get("intent", "unknown") in {"chat", "unknown"}:
        other_request = (
            _is_summary_intent(text) or _is_update_intent(text) or _is_delete_intent(text)
            or re.search(r"覚え|記憶|今後|これから|しないで|登録しない|買いたい|買おう|予算|ですか|？|\?", text)
        )
        expense = _has_amount(text) or re.search(r"買っ|買って|かって|購入した|払っ|支払った|登録|記録|入れといて", text)
        if expense and not other_request:
            bedrock_intent = {**(bedrock_intent or {}), "intent": "create_ticket"}
    if settings.line_agent_mode == "bedrock" and (not pending or pending.get("intent") == "create_ticket") and (bedrock_intent or {}).get("intent") == "create_ticket":
        title = _clean_ai_title(bedrock_intent.get("title"))
        comment = _clean_ai_title(bedrock_intent.get("friendly_comment"))
        if not title or title == _clean_ai_title(text) or not comment or comment.startswith("了解！"):
            # A single bounded repair fills presentation fields, never amounts or ratios.
            proposal = _try_bedrock_intent(text, categories, memories, store.list_tags(), pending, proposal_only=True)
            if proposal:
                for key in ("title", "friendly_comment", "category"):
                    if _clean_ai_title(proposal.get(key)):
                        bedrock_intent[key] = proposal[key]
    _diagnostic_log("agent_preferences_loaded", details={"memory_ids": [r["id"] for r in memories]})
    try:
        preference_reply = preference_command(text, bedrock_intent or {}, user, store)
        if preference_reply:
            return AgentResult(reply=preference_reply)
        if (bedrock_intent or {}).get("intent") == "remember":
            content = str(bedrock_intent.get("memory_content") or "").strip()
            if not content or len(content) > 500:
                return AgentResult(reply="今後の注意事項として保存したい内容を、500文字以内で教えてください。")
            scope = memory_scope(text)
            label = "共通" if scope == "shared" else f"{user['name']}向け"
            _save_pending(store, line_user_id, {"intent": "confirm_memory", "content": content, "scope": scope, "resume": pending})
            return AgentResult(reply=f"{label}の注意事項として保存しますか？\n{content}\nまだ保存していません。", quick_replies=["この方針を保存", "保存しない"])
        resolve_tag_ids(text, bedrock_intent or {}, store)
    except ValueError as exc:
        return AgentResult(reply=str(exc))

    if pending and pending.get("intent") == "confirm_create":
        if bedrock_intent and bedrock_intent.get("intent") in {"chat", "unknown"}:
            return _unknown_reply(bedrock_intent)
        if bedrock_intent and bedrock_intent.get("intent") == "summary":
            _clear_pending(store, line_user_id)
            result = _maybe_answer_summary(text, user, store, bedrock_intent)
            if result:
                result.trace.insert(0, "Bedrock\u3067\u8cea\u554f\u610f\u56f3\u3068\u671f\u9593\u3092\u5224\u5b9a")
                return result
        return _confirm_create(text, user, store, line_user_id, bedrock_intent)
    if pending and pending.get("intent") == "select_delete_candidate":
        return _handle_delete(text, user, store, line_user_id, ai=bedrock_intent)
    if pending and pending.get("intent") == "confirm_delete":
        return _handle_delete(text, user, store, line_user_id)
    if pending and pending.get("intent") in {"confirm_update", "edit_update"}:
        return _handle_update(text, user, store, line_user_id, ai=bedrock_intent)
    if pending and pending.get("intent") == "create_ticket":
        if bedrock_intent and bedrock_intent.get("intent") in {"chat", "unknown"}:
            return _unknown_reply(bedrock_intent)
        if bedrock_intent and bedrock_intent.get("intent") == "summary":
            _clear_pending(store, line_user_id)
            result = _maybe_answer_summary(text, user, store, bedrock_intent)
            if result:
                result.trace.insert(0, "Bedrock\u3067\u8cea\u554f\u610f\u56f3\u3068\u671f\u9593\u3092\u5224\u5b9a")
                return result
        if bedrock_intent and bedrock_intent.get("intent") == "delete_ticket":
            _clear_pending(store, line_user_id)
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_delete(text, user, store, line_user_id, ticket, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u524a\u9664\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if bedrock_intent and bedrock_intent.get("intent") == "update_ticket":
            _clear_pending(store, line_user_id)
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_update(text, user, store, line_user_id, ticket, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u66f4\u65b0\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        return _create_ticket_candidate(text, user, store, line_user_id, bedrock_intent)

    if bedrock_intent:
        intent = bedrock_intent.get("intent")
        if intent == "summary":
            _clear_pending(store, line_user_id)
            result = _maybe_answer_summary(text, user, store, bedrock_intent)
            if result:
                result.trace.insert(0, "Bedrock\u3067\u8cea\u554f\u610f\u56f3\u3068\u671f\u9593\u3092\u5224\u5b9a")
                return result
        if intent == "create_ticket":
            result = _confirm_create(text, user, store, line_user_id, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u767b\u9332\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if intent == "delete_ticket":
            _clear_pending(store, line_user_id)
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_delete(text, user, store, line_user_id, ticket, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u524a\u9664\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if intent == "update_ticket":
            _clear_pending(store, line_user_id)
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_update(text, user, store, line_user_id, ticket, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u66f4\u65b0\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if intent == "chat":
            return _unknown_reply(bedrock_intent)
        if intent == "unknown":
            if _is_delete_intent(text):
                _clear_pending(store, line_user_id)
                return _handle_delete(text, user, store, line_user_id, ai=bedrock_intent)
            if _is_update_intent(text):
                _clear_pending(store, line_user_id)
                return _handle_update(text, user, store, line_user_id, ai=bedrock_intent)
            return _unknown_reply(bedrock_intent)

    if _is_summary_intent(text):
        _clear_pending(store, line_user_id)
        result = _maybe_answer_summary(text, user, store)
        if result:
            return result

    if _is_delete_intent(text):
        _clear_pending(store, line_user_id)
        return _handle_delete(text, user, store, line_user_id, ai=bedrock_intent)
    if _is_update_intent(text):
        _clear_pending(store, line_user_id)
        return _handle_update(text, user, store, line_user_id)
    if _is_register_intent(text, store):
        return _confirm_create(text, user, store, line_user_id)

    return _unknown_reply()
