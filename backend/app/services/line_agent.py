from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import boto3

from app.core.config import settings
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.store import DynamoStore

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_RATIO = 5
UNCATEGORIZED = "\u672a\u6307\u5b9a"


@dataclass
class AgentResult:
    reply: str
    ticket: dict[str, Any] | None = None
    quick_replies: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


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


def _category_breakdown(tickets: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for ticket in tickets:
        category = ticket.get("category") or UNCATEGORIZED
        totals[category] = totals.get(category, 0) + int(ticket["amount"])
        counts[category] = counts.get(category, 0) + 1
    return sorted(((name, totals[name], counts[name]) for name in totals), key=lambda row: row[1], reverse=True)


def _format_trace(trace: list[str]) -> str:
    if not settings.line_agent_trace_enabled or not trace:
        return ""
    lines = ["", "----", "\u51e6\u7406\u30ed\u30b0"]
    lines.extend(f"- {item}" for item in trace[:6])
    return "\n".join(lines)


def _tool_log(store: DynamoStore, user: dict[str, Any], tool_name: str, trace: list[str], result: dict[str, Any] | None = None) -> None:
    store.write_audit("ai_tool_call", "ai_agent", user["id"], None, after={"tool": tool_name, "trace": trace, "result": result or {}})


def _maybe_answer_summary(text: str, user: dict[str, Any], store: DynamoStore) -> AgentResult | None:
    wants_summary = _is_summary_intent(text)
    if not wants_summary:
        return None

    trace = ["\u8cea\u554f\u610f\u56f3\u3092\u96c6\u8a08\u30fb\u5206\u6790\u3068\u3057\u3066\u5224\u5b9a"]
    if "\u4eca\u5e74" in text or "\u5e74" in text:
        from_date, to_date, label = _period_year()
    elif "\u5148\u6708" in text:
        from_date, to_date, label = _period_month(-1)
    else:
        from_date, to_date, label = _period_month(0)
    trace.append(f"\u5bfe\u8c61\u671f\u9593\u3092{label}\u306b\u8a2d\u5b9a")

    tickets = store.list_tickets(from_date, to_date, statuses=["new", "settled"])
    summary = store.summarize(from_date, to_date, ["new", "settled"])
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

    if "\u5148\u6708" not in text and any(word in text for word in ["\u50be\u5411", "\u6bd4\u8f03", "\u6bd4\u3079"]):
        prev_from, prev_to, prev_label = _period_month(-1)
        prev = store.summarize(prev_from, prev_to, ["new", "settled"])
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
        "\u4eca\u6708",
        "\u5148\u6708",
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
        or any(word in text for word in ["\u50be\u5411", "\u96c6\u8a08", "\u5185\u8a33", "\u30e9\u30f3\u30ad\u30f3\u30b0", "\u6bd4\u8f03", "\u6bd4\u3079", "\u5229\u7528\u91d1\u984d", "\u5229\u7528\u984d", "\u652f\u51fa", "1\u304b\u6708", "1\u30f6\u6708", "\uff11\u304b\u6708", "\uff11\u30f6\u6708"])
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
    expires_at = row.get("expires_at")
    if expires_at and expires_at < datetime.now(JST).isoformat():
        store._delete("AGENT_SESSION", _pending_key(line_user_id))
        return None
    return row


def _save_pending(store: DynamoStore, line_user_id: str, payload: dict[str, Any]) -> None:
    expires_at = (datetime.now(JST) + timedelta(minutes=10)).isoformat()
    store._put("AGENT_SESSION", _pending_key(line_user_id), {**payload, "expires_at": expires_at})


def _clear_pending(store: DynamoStore, line_user_id: str) -> None:
    store._delete("AGENT_SESSION", _pending_key(line_user_id))


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
    }


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
    )


def _confirm_create(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    if not pending or pending.get("intent") != "confirm_create":
        return _create_ticket_candidate(text, user, store, line_user_id, ai)

    if _is_confirm_yes(text, "\u767b\u9332\u3059\u308b"):
        payload = _ticket_payload_from_dict(pending["payload"])
        ticket = store.create_ticket(payload, UUID(user["id"]))
        store.write_audit("ticket_create", "ticket", user["id"], ticket["id"], after=store.ticket_audit_dict(ticket))
        _clear_pending(store, line_user_id)
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
        _clear_pending(store, line_user_id)
        return AgentResult(reply="\u767b\u9332\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    return AgentResult(
        reply="\u767b\u9332\u5f85\u3061\u306e\u5019\u88dc\u304c\u3042\u308a\u307e\u3059\u3002\u767b\u9332\u3057\u307e\u3059\u304b\uff1f",
        quick_replies=["\u767b\u9332\u3059\u308b", "\u3084\u3081\u308b"],
    )


def _create_ticket_candidate(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, ai: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    base_text = f"{pending.get('text', '')} {text}" if pending and pending.get("intent") == "create_ticket" and _is_amount_only_reply(text) else text
    trace: list[str] = ["\u5165\u529b\u6587\u3092\u30c1\u30b1\u30c3\u30c8\u4f5c\u6210\u5019\u88dc\u3068\u3057\u3066\u89e3\u6790"]
    ai = ai or {}

    amount, amount_trace = _parse_amount(base_text)
    parsed_date, date_trace = _parse_date(base_text)
    category, category_trace = _parse_category(base_text, store)
    status = _parse_status(base_text)
    ai_title = _clean_ai_title(ai.get("title"))
    ai_category = _clean_ai_title(ai.get("category"))
    ai_amount = ai.get("amount")
    ai_date = ai.get("date")
    if isinstance(ai_amount, (int, float)) and not amount:
        amount = int(ai_amount)
        amount_trace = "Bedrock\u3067\u91d1\u984d\u3092\u62bd\u51fa"
    if ai_category and not category:
        category = ai_category
        category_trace = "Bedrock\u3067\u30ab\u30c6\u30b4\u30ea\u3092\u63a8\u5b9a"
    if isinstance(ai.get("status"), str) and ai["status"] in ["new", "settled", "canceled"]:
        status = ai["status"]
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
    if not parsed_date:
        parsed_date = _today()
        trace.append("\u65e5\u4ed8\u6307\u5b9a\u304c\u306a\u3044\u305f\u3081\u4eca\u65e5\u306e\u65e5\u4ed8\u3092\u4f7f\u7528")

    if not amount:
        _save_pending(store, line_user_id, {"intent": "create_ticket", "text": base_text})
        trace.append("\u91d1\u984d\u304c\u4e0d\u8db3\u3057\u3066\u3044\u308b\u305f\u3081\u805e\u304d\u8fd4\u3057")
        _tool_log(store, user, "ask_missing_amount", trace)
        return AgentResult(
            reply="\u91d1\u984d\u304c\u5206\u304b\u308a\u307e\u305b\u3093\u3002\u3044\u304f\u3089\u3067\u3057\u305f\u304b\uff1f\n\u4f8b: 3200\u5186" + _format_trace(trace),
            quick_replies=["1000\u5186", "3000\u5186", "5000\u5186"],
            trace=trace,
        )

    title = ai_title or _guess_title(base_text, category)
    payload = TicketCreate(
        date=parsed_date,
        title=title,
        amount=amount,
        payer_user_id=UUID(user["id"]),
        ratio_f=DEFAULT_RATIO,
        ratio_o=DEFAULT_RATIO,
        status=status,
        category=category,
        memo=f"LINE\u304b\u3089\u767b\u9332: {base_text.strip()}",
    )
    _save_pending(store, line_user_id, {"intent": "confirm_create", "payload": _ticket_payload_dict(payload), "trace": trace})
    trace.append("\u767b\u9332\u524d\u78ba\u8a8d\u3092\u4f5c\u6210")
    reply = (
        "\u4ee5\u4e0b\u306e\u5185\u5bb9\u3067\u767b\u9332\u3057\u307e\u3059\u304b\uff1f\n"
        f"\u4ef6\u540d: {payload.title}\n"
        f"\u65e5\u4ed8: {payload.date.isoformat()}\n"
        f"\u91d1\u984d: {_format_yen(payload.amount)}\n"
        f"\u30ab\u30c6\u30b4\u30ea: {payload.category or UNCATEGORIZED}\n"
        f"\u7acb\u66ff: {user['name']}\n"
        "\u8ca0\u62c5\u6bd4\u7387: 50% / 50%"
    )
    return AgentResult(reply=reply + _format_trace(trace), quick_replies=["\u767b\u9332\u3059\u308b", "\u3084\u3081\u308b"], trace=trace)


def _find_ticket_by_display_id(store: DynamoStore, display_id: int) -> dict[str, Any] | None:
    return next((ticket for ticket in store.list_tickets(statuses=["new", "settled", "canceled"]) if ticket.get("display_id") == display_id), None)


def _parse_display_id(text: str) -> int | None:
    match = re.search(r"(?:\u30c1\u30b1\u30c3\u30c8ID|ID|#)\s*[:\uff1a]?\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_delete_intent(text: str) -> bool:
    return any(word in text for word in ["\u524a\u9664", "\u6d88\u3057\u3066", "\u53d6\u308a\u6d88\u3057", "\u6d88\u3059"]) and (_parse_display_id(text) is not None or _is_recent_reference(text))


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


def _handle_delete(text: str, user: dict[str, Any], store: DynamoStore, line_user_id: str, target_ticket: dict[str, Any] | None = None) -> AgentResult:
    pending = _get_pending(store, line_user_id)
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
        return AgentResult(reply="\u524a\u9664\u5bfe\u8c61\u306e\u30c1\u30b1\u30c3\u30c8ID\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\n\u4f8b: \u30c1\u30b1\u30c3\u30c8ID 10 \u524a\u9664")
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
    if pending and pending.get("intent") == "confirm_update":
        ticket_id = pending["ticket_id"]
        if _is_confirm_yes(text, "\u66f4\u65b0\u3059\u308b"):
            try:
                before, ticket = store.update_ticket(UUID(ticket_id), _ticket_update_from_dict(pending["payload"]), UUID(user["id"]))
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
        return AgentResult(reply="\u66f4\u65b0\u5bfe\u8c61\u306e\u30c1\u30b1\u30c3\u30c8ID\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\n\u4f8b: \u30c1\u30b1\u30c3\u30c8ID 10 \u91d1\u984d 3500\u5186\u306b\u5909\u66f4")

    amount, amount_trace = _parse_amount(text)
    parsed_date, date_trace = _parse_date(text)
    category, category_trace = _parse_category(text, store)
    status = _parse_status(text)
    ai = ai or {}
    ai_title = _clean_ai_title(ai.get("title"))
    ai_amount = ai.get("amount")
    ai_date = ai.get("date")
    ai_category = _clean_ai_title(ai.get("category"))
    try:
        if ai_date and not parsed_date:
            parsed_date = datetime.strptime(str(ai_date), "%Y-%m-%d").date()
            date_trace = "Bedrock\u3067\u65e5\u4ed8\u3092\u88dc\u5b8c"
    except ValueError:
        pass
    payload = TicketUpdate(
        date=parsed_date or datetime.strptime(ticket["date"], "%Y-%m-%d").date(),
        title=ai_title or ticket["title"],
        amount=amount or (int(ai_amount) if isinstance(ai_amount, (int, float)) else int(ticket["amount"])),
        payer_user_id=UUID(ticket["payer_user_id"]),
        ratio_f=int(ticket["ratio_f"]),
        ratio_o=int(ticket["ratio_o"]),
        status=status if status != "new" or "\u672a\u7cbe\u7b97" in text else ticket["status"],
        category=category or ai_category or ticket.get("category") or "",
        memo=ticket.get("memo") or "",
    )
    trace = ["update_ticket\u30c4\u30fc\u30eb\u306e\u5b9f\u884c\u524d\u78ba\u8a8d\u3092\u4f5c\u6210"]
    if amount_trace:
        trace.append(amount_trace)
    if date_trace:
        trace.append(date_trace)
    if category_trace:
        trace.append(category_trace)
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
    return AgentResult(reply=reply + _format_trace(trace), quick_replies=["\u66f4\u65b0\u3059\u308b", "\u3084\u3081\u308b"], trace=trace)


def _try_bedrock_intent(text: str, categories: list[str]) -> dict[str, Any] | None:
    if settings.line_agent_mode != "bedrock":
        return None
    try:
        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        prompt = (
            "\u3042\u306a\u305f\u306f2\u4eba\u7528\u5bb6\u8a08\u7c3f\u306eLINE\u5165\u529b\u3092\u89e3\u6790\u3059\u308b\u30a8\u30fc\u30b8\u30a7\u30f3\u30c8\u3067\u3059\u3002"
            "\u51fa\u529b\u306fJSON\u306e\u307f\u3002Markdown\u306f\u4f7f\u308f\u306a\u3044\u3002"
            "schema={\"intent\":\"create_ticket|summary|update_ticket|delete_ticket|unknown\","
            "\"title\":\"\u77ed\u304f\u81ea\u7136\u306a\u4ef6\u540d\u3002\u4f8b:\u30b9\u30fc\u30d1\u30fc,\u30ab\u30d5\u30a7,\u5bb6\u8cc3\","
            "\"amount\":number|null,\"date\":\"YYYY-MM-DD|null\",\"category\":\"string|null\","
            "\"status\":\"new|settled|canceled|null\",\"target_display_id\":number|null,"
            "\"target_reference\":\"recent|explicit|null\"}."
            "\u300c\u3055\u3063\u304d\u306e\u30c1\u30b1\u30c3\u30c8\u300d\u300c\u76f4\u8fd1\u306e\u30c1\u30b1\u30c3\u30c8\u300d\u306ftarget_reference=recent\u3002"
            "\u524a\u9664\u3001\u6d88\u3057\u3066\u3001\u53d6\u308a\u6d88\u3057\u306fdelete_ticket\u3002"
            "\u4fee\u6b63\u3001\u5909\u66f4\u3001\u76f4\u3057\u3066\u306fupdate_ticket\u3002"
            "\u652f\u51fa\u3084\u50be\u5411\u3084\u5408\u8a08\u306e\u8cea\u554f\u306fsummary\u3002"
            "\u4ef6\u540d\u306f\u91d1\u984d\u3001\u65e5\u4ed8\u3001\u300c\u767b\u9332\u300d\u300c\u5165\u308c\u3068\u3044\u3066\u300d\u3092\u542b\u3081\u306a\u3044\u3002"
            f"\u30ab\u30c6\u30b4\u30ea\u5019\u88dc: {', '.join(categories)}\n"
            f"\u4eca\u65e5: {_today().isoformat()}\n"
            f"\u5165\u529b: {text}"
        )
        response = client.converse(
            modelId=settings.bedrock_model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0},
        )
        content = response["output"]["message"]["content"][0]["text"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        return json.loads(match.group(0) if match else content)
    except Exception:
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


def handle_line_text(text: str, line_user_id: str, user: dict[str, Any], store: DynamoStore) -> AgentResult:
    pending = _get_pending(store, line_user_id)
    if _is_cancel_text(text):
        _clear_pending(store, line_user_id)
        return AgentResult(reply="\u9032\u884c\u4e2d\u306e\u64cd\u4f5c\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f\u3002")

    if _is_summary_intent(text):
        _clear_pending(store, line_user_id)
        result = _maybe_answer_summary(text, user, store)
        if result:
            return result

    if _is_delete_intent(text):
        _clear_pending(store, line_user_id)
        return _handle_delete(text, user, store, line_user_id)
    if _is_update_intent(text):
        _clear_pending(store, line_user_id)
        return _handle_update(text, user, store, line_user_id)
    if pending and pending.get("intent") == "confirm_create" and _is_register_intent(text, store) and not _is_confirm_yes(text, "\u767b\u9332\u3059\u308b"):
        _clear_pending(store, line_user_id)
        return _confirm_create(text, user, store, line_user_id)
    if pending and pending.get("intent") == "create_ticket" and _is_register_intent(text, store) and not _is_amount_only_reply(text):
        _clear_pending(store, line_user_id)
        return _confirm_create(text, user, store, line_user_id)

    if pending and pending.get("intent") == "confirm_create":
        return _confirm_create(text, user, store, line_user_id)
    if pending and pending.get("intent") == "confirm_delete":
        return _handle_delete(text, user, store, line_user_id)
    if pending and pending.get("intent") == "confirm_update":
        return _handle_update(text, user, store, line_user_id)

    categories = [row["name"] for row in store.list_categories()]
    bedrock_intent = _try_bedrock_intent(text, categories)
    if bedrock_intent:
        intent = bedrock_intent.get("intent")
        if intent == "summary":
            result = _maybe_answer_summary(text, user, store)
            if result:
                result.trace.insert(0, "Bedrock\u3067\u8cea\u554f\u610f\u56f3\u3092\u5224\u5b9a")
                return result
        if intent == "create_ticket":
            result = _confirm_create(text, user, store, line_user_id, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u767b\u9332\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if intent == "delete_ticket":
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_delete(text, user, store, line_user_id, ticket)
            result.trace.insert(0, "Bedrock\u3067\u524a\u9664\u610f\u56f3\u3092\u5224\u5b9a")
            return result
        if intent == "update_ticket":
            ticket = _ticket_from_ai_target(bedrock_intent, user, store)
            result = _handle_update(text, user, store, line_user_id, ticket, bedrock_intent)
            result.trace.insert(0, "Bedrock\u3067\u66f4\u65b0\u610f\u56f3\u3092\u5224\u5b9a")
            return result

    if _is_register_intent(text, store):
        return _confirm_create(text, user, store, line_user_id)

    return AgentResult(
        reply=(
            "\u3084\u308a\u305f\u3044\u64cd\u4f5c\u3092\u8aad\u307f\u53d6\u308c\u307e\u305b\u3093\u3067\u3057\u305f\u3002\n"
            "\u4f8b:\n"
            "\u6628\u65e5\u30b9\u30fc\u30d1\u30fc\u30673200\u5186\n"
            "\u4eca\u6708\u306e\u5229\u7528\u91d1\u984d\u6559\u3048\u3066\n"
            "\u30c1\u30b1\u30c3\u30c8ID 10 \u91d1\u984d 3500\u5186\u306b\u5909\u66f4\n"
            "\u30c1\u30b1\u30c3\u30c8ID 10 \u524a\u9664"
        )
    )
