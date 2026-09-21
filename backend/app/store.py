from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from time import sleep
from typing import Any
from uuid import UUID, uuid4

import boto3
from boto3.dynamodb.conditions import Key

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.secrets import initial_user_password
from app.schemas.ticket import TicketCreate, TicketUpdate


DEFAULT_CATEGORIES = [
    ("食費", "スーパー、コンビニ、食材、飲料など", "utensils", "#f9736b"),
    ("外食", "レストラン、カフェ、デリバリーなど", "restaurant", "#fb923c"),
    ("日用品", "洗剤、ティッシュ、生活雑貨など", "shopping-basket", "#eab308"),
    ("住居", "家賃、管理費、更新料、家具など", "house", "#8b5cf6"),
    ("水道・光熱費", "電気、ガス、水道など", "zap", "#06b6d4"),
    ("通信費", "スマホ、インターネット、郵送料など", "smartphone", "#3b82f6"),
    ("交通費", "電車、バス、タクシー、ガソリンなど", "train", "#14b8a6"),
    ("医療・健康", "病院、薬、健康診断、ジムなど", "heart-pulse", "#ef476f"),
    ("衣服・美容", "服、靴、美容院、化粧品など", "sparkles", "#ec4899"),
    ("娯楽・趣味", "ゲーム、映画、旅行、サブスクなど", "gamepad", "#6366f1"),
    ("その他", "上記に分類しにくい支出", "shapes", "#64748b"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def calculate_shares(amount: int, ratio_f: int, ratio_o: int) -> tuple[int, int]:
    total = ratio_f + ratio_o
    if total <= 0:
        raise ValueError("ratio total must be greater than zero")
    share_f = round(amount * ratio_f / total)
    return share_f, amount - share_f


class DynamoStore:
    def __init__(self) -> None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        self.resource = boto3.resource("dynamodb", **kwargs)
        self.table = self.resource.Table(settings.dynamodb_table_name)

    def ensure_table(self) -> None:
        last_error: Exception | None = None
        for _ in range(20):
            try:
                self.table.load()
                return
            except Exception as exc:
                last_error = exc
                if not settings.dynamodb_auto_create:
                    raise
                sleep(0.5)
        self.table = self.resource.create_table(
            TableName=settings.dynamodb_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        self.table.wait_until_exists()

    def _put(self, kind: str, item_id: str, item: dict[str, Any]) -> dict[str, Any]:
        row = {"pk": kind, "sk": item_id, "entity": kind, **jsonable(item)}
        self.table.put_item(Item=row)
        return clean(row)

    def _delete(self, kind: str, item_id: str) -> None:
        self.table.delete_item(Key={"pk": kind, "sk": item_id})

    def _get(self, kind: str, item_id: str) -> dict[str, Any] | None:
        res = self.table.get_item(Key={"pk": kind, "sk": item_id})
        item = res.get("Item")
        return clean(item) if item else None

    def _items(self, kind: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        params: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(kind)}
        while True:
            res = self.table.query(**params)
            rows.extend(clean(res.get("Items", [])))
            if "LastEvaluatedKey" not in res:
                break
            params["ExclusiveStartKey"] = res["LastEvaluatedKey"]
        return rows

    def seed_users(self) -> None:
        password = initial_user_password()
        for name, email in [
            (settings.initial_user_1_name, "f@example.com"),
            (settings.initial_user_2_name, "o@example.com"),
        ]:
            user = self.get_user_by_email(email)
            item = user or {"id": str(uuid4()), "email": email, "name": name, "line_user_id": None}
            item.setdefault("line_user_id", None)
            item["password_hash"] = hash_password(password)
            self._put("USER", item["id"], item)

    def list_users(self) -> list[dict[str, Any]]:
        return sorted(self._items("USER"), key=lambda row: row["email"])

    def get_user(self, user_id: UUID | str) -> dict[str, Any] | None:
        return self._get("USER", str(user_id))

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return next((row for row in self._items("USER") if row["email"] == email), None)

    def get_user_by_line_user_id(self, line_user_id: str) -> dict[str, Any] | None:
        return next((row for row in self._items("USER") if row.get("line_user_id") == line_user_id), None)

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.get_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            return None
        return user

    def update_user_profile(self, user_id: UUID, name: str, line_user_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            raise KeyError("user")
        before = {"name": user["name"], "line_user_id": user.get("line_user_id")}
        user["name"] = name[:40]
        user["line_user_id"] = line_user_id[:80] if line_user_id else None
        self._put("USER", user["id"], user)
        return before, user

    def get_closing_day(self) -> int:
        row = self._get("SETTING", "closing_day")
        return int(row["value"]) if row else 31

    def update_closing_day(self, closing_day: int) -> tuple[dict[str, Any], dict[str, Any]]:
        before = {"closing_day": self.get_closing_day()}
        after = {"closing_day": closing_day}
        self._put("SETTING", "closing_day", {"key": "closing_day", "value": closing_day})
        return before, after

    def list_categories(self) -> list[dict[str, Any]]:
        return sorted(self._items("CATEGORY"), key=lambda row: row["name"])

    def seed_categories(self) -> None:
        existing_by_name = {row["name"]: row for row in self._items("CATEGORY")}
        for name, description, icon, color in DEFAULT_CATEGORIES:
            existing = existing_by_name.get(name)
            category_id = existing["id"] if existing else str(uuid4())
            self._put("CATEGORY", category_id, {
                **(existing or {}),
                "id": category_id,
                "name": name,
                "description": description,
                "icon": icon,
                "color": existing.get("color", color) if existing else color,
                "is_default": True,
            })

    def create_category(self, name: str, color: str) -> dict[str, Any]:
        row = {"id": str(uuid4()), "name": name.strip(), "color": color, "description": "", "icon": "tag", "is_default": False}
        return self._put("CATEGORY", row["id"], row)

    def update_category(self, category_id: UUID, name: str, color: str) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self._get("CATEGORY", str(category_id))
        if not row:
            raise KeyError("category")
        before = {"name": row["name"], "color": row["color"]}
        row.update({"name": name.strip(), "color": color})
        self._put("CATEGORY", row["id"], row)
        return before, row

    def delete_category(self, category_id: UUID) -> dict[str, Any] | None:
        row = self._get("CATEGORY", str(category_id))
        if row:
            self._delete("CATEGORY", str(category_id))
        return row

    def list_templates(self) -> list[dict[str, Any]]:
        return sorted(self._items("TEMPLATE"), key=lambda row: row["name"])

    def list_tags(self) -> list[dict[str, Any]]:
        return sorted(self._items("TAG"), key=lambda row: row["name"])

    def save_tag(self, name: str, tag_id: str | None = None) -> dict[str, Any]:
        name = name.strip().lstrip("#＃").strip()
        if not name or len(name) > 60:
            raise ValueError("タグ名は1〜60文字で指定してください。")
        if tag_id and not self._get("TAG", tag_id):
            raise ValueError("タグが見つかりません。")
        existing = next((row for row in self.list_tags() if row["name"] == name), None)
        if existing:
            if tag_id and existing["id"] != tag_id:
                raise ValueError("同じ名前のタグがあります。")
            return existing
        row = {"id": tag_id or str(uuid4()), "name": name}
        return self._put("TAG", row["id"], row)

    def delete_tag(self, tag_id: str) -> None:
        if any(tag_id in row.get("tag_ids", []) for row in self._items("TICKET") if not row.get("deleted_at")):
            raise ValueError("使用中のタグは削除できません。先にチケットから外してください。")
        self._delete("TAG", tag_id)

    @staticmethod
    def _memory_partition(user_id: str, scope: str) -> str:
        if scope not in {"personal", "shared"}:
            raise ValueError("記憶の範囲が不正です。")
        return "AGENT_MEMORY_SHARED" if scope == "shared" else f"AGENT_MEMORY#{user_id}"

    def list_memories(self, user_id: str, scope: str = "personal") -> list[dict[str, Any]]:
        return [{**row, "scope": scope} for row in sorted(self._items(self._memory_partition(user_id, scope)), key=lambda row: row["created_at"])]

    def save_memory(self, user_id: str, content: str, scope: str = "personal") -> dict[str, Any]:
        content = content.strip()
        if not content or len(content) > 500:
            raise ValueError("記憶は1〜500文字で指定してください。")
        memories = self.list_memories(user_id, scope)
        existing = next((row for row in memories if row["content"] == content), None)
        if existing:
            return existing
        if len(memories) >= 30:
            raise ValueError("記憶は30件までです。設定で不要な記憶を削除してください。")
        row = {"id": str(uuid4()), "content": content, "created_at": now_iso()}
        return self._put(self._memory_partition(user_id, scope), row["id"], {**row, "scope": scope})

    def delete_memory(self, user_id: str, memory_id: str, scope: str = "personal") -> None:
        self._delete(self._memory_partition(user_id, scope), memory_id)

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"id": str(uuid4()), **jsonable(payload)}
        return self._put("TEMPLATE", row["id"], row)

    def update_template(self, template_id: UUID, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self._get("TEMPLATE", str(template_id))
        if not row:
            raise KeyError("template")
        before = {key: row.get(key) for key in ["name", "title", "amount", "payer_user_id", "ratio_f", "ratio_o", "status", "category", "memo"]}
        row.update(jsonable(payload))
        self._put("TEMPLATE", row["id"], row)
        return before, row

    def delete_template(self, template_id: UUID) -> dict[str, Any] | None:
        row = self._get("TEMPLATE", str(template_id))
        if row:
            self._delete("TEMPLATE", str(template_id))
        return row

    def get_monthly_settlement(self, period_key: str) -> dict[str, Any]:
        return self._get("MONTHLY", period_key) or {
            "period_key": period_key,
            "status": "new",
            "memo": "",
            "closing_day": self.get_closing_day(),
        }

    def update_monthly_settlement(self, period_key: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        before = self.get_monthly_settlement(period_key)
        row = {"period_key": period_key, **jsonable(payload)}
        self._put("MONTHLY", period_key, row)
        return before, row

    def _ticket_from_payload(self, payload: TicketCreate | TicketUpdate, actor_id: UUID, ticket: dict[str, Any] | None = None) -> dict[str, Any]:
        tag_ids = list(dict.fromkeys(str(value) for value in payload.tag_ids))
        if any(not self._get("TAG", tag_id) for tag_id in tag_ids):
            raise ValueError("設定に存在しないタグが指定されています。")
        share_f, share_o = calculate_shares(payload.amount, payload.ratio_f, payload.ratio_o)
        timestamp = now_iso()
        row = ticket.copy() if ticket else {
            "id": str(uuid4()),
            "created_by": str(actor_id),
            "created_at": timestamp,
            "deleted_at": None,
        }
        row.pop("display_id", None)
        row.update({
            "date": payload.date.isoformat(),
            "title": payload.title,
            "amount": payload.amount,
            "payer_user_id": str(payload.payer_user_id),
            "ratio_f": payload.ratio_f,
            "ratio_o": payload.ratio_o,
            "share_f": share_f,
            "share_o": share_o,
            "status": payload.status,
            "category": payload.category.strip() or "その他",
            "memo": payload.memo,
            "tag_ids": tag_ids,
            "updated_by": str(actor_id),
            "updated_at": timestamp,
        })
        return row

    def create_ticket(self, payload: TicketCreate, actor_id: UUID) -> dict[str, Any]:
        row = self._ticket_from_payload(payload, actor_id)
        self._put("TICKET", row["id"], row)
        return self.with_payer_name(row)

    def get_ticket(self, ticket_id: UUID) -> dict[str, Any] | None:
        row = self._get("TICKET", str(ticket_id))
        if not row or row.get("deleted_at"):
            return None
        return self.with_payer_name(row)

    def list_tickets(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | None = None,
        statuses: list[str] | None = None,
        category: str | None = None,
        payer_user_id: UUID | None = None,
        keyword: str | None = None,
        tag_id: str | None = None,
        tag_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = [row for row in self._items("TICKET") if not row.get("deleted_at")]
        if from_date:
            rows = [row for row in rows if row["date"] >= from_date.isoformat()]
        if to_date:
            rows = [row for row in rows if row["date"] <= to_date.isoformat()]
        if statuses is not None:
            rows = [row for row in rows if row["status"] in statuses]
        elif status:
            rows = [row for row in rows if row["status"] == status]
        else:
            rows = [row for row in rows if row["status"] != "canceled"]
        if category:
            rows = [row for row in rows if (row.get("category") or "その他") == category]
        if payer_user_id:
            rows = [row for row in rows if row["payer_user_id"] == str(payer_user_id)]
        if keyword:
            rows = [row for row in rows if keyword.lower() in row["title"].lower()]
        selected_tag_ids = set(tag_ids or ([tag_id] if tag_id else []))
        if selected_tag_ids:
            rows = [row for row in rows if selected_tag_ids.intersection(row.get("tag_ids", []))]
        rows.sort(key=lambda row: (row["date"], row["created_at"]), reverse=True)
        display_ids = self.ticket_display_ids()
        return [self.with_payer_name(row, display_ids) for row in rows]

    def update_ticket(self, ticket_id: UUID, payload: TicketUpdate, actor_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self.get_ticket(ticket_id)
        if not row:
            raise KeyError("ticket")
        before = self.ticket_audit_dict(row)
        updated = self._ticket_from_payload(payload, actor_id, row)
        self._put("TICKET", updated["id"], updated)
        return before, self.with_payer_name(updated)

    def delete_ticket(self, ticket_id: UUID, actor_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self.get_ticket(ticket_id)
        if not row:
            raise KeyError("ticket")
        before = self.ticket_audit_dict(row)
        row["deleted_at"] = now_iso()
        row["updated_by"] = str(actor_id)
        row["updated_at"] = row["deleted_at"]
        self._put("TICKET", row["id"], row)
        return before, {"deleted_at": row["deleted_at"]}

    def bulk_status(self, from_date: date, to_date: date, actor_id: UUID) -> tuple[int, list[str]]:
        rows = self.list_tickets(from_date, to_date, status="new")
        ids: list[str] = []
        timestamp = now_iso()
        for row in rows:
            row["status"] = "settled"
            row["updated_by"] = str(actor_id)
            row["updated_at"] = timestamp
            self._put("TICKET", row["id"], row)
            ids.append(row["id"])
        return len(ids), ids

    def bulk_add_tags(self, ticket_ids: list[str], tag_ids: list[str], actor_id: UUID) -> tuple[int, list[str]]:
        unique_ticket_ids = list(dict.fromkeys(ticket_ids))
        unique_tag_ids = list(dict.fromkeys(tag_ids))
        if not unique_ticket_ids:
            raise ValueError("チケットを1件以上選択してください。")
        if not unique_tag_ids:
            raise ValueError("追加するタグを1件以上選択してください。")
        if any(not self._get("TAG", tag_id) for tag_id in unique_tag_ids):
            raise ValueError("設定に存在しないタグが指定されています。")

        rows: list[dict[str, Any]] = []
        for ticket_id in unique_ticket_ids:
            row = self._get("TICKET", ticket_id)
            if not row or row.get("deleted_at"):
                raise ValueError("選択したチケットが見つかりません。再読み込みしてください。")
            rows.append(row)

        timestamp = now_iso()
        updated_ids: list[str] = []
        for row in rows:
            before = row.get("tag_ids", [])
            after = list(dict.fromkeys([*before, *unique_tag_ids]))
            if after == before:
                continue
            row["tag_ids"] = after
            row["updated_by"] = str(actor_id)
            row["updated_at"] = timestamp
            self._put("TICKET", row["id"], row)
            updated_ids.append(row["id"])
        return len(updated_ids), updated_ids

    def ticket_display_ids(self) -> dict[str, int]:
        rows = [row for row in self._items("TICKET") if not row.get("deleted_at")]
        rows.sort(key=lambda row: (row["date"], row["created_at"], row["id"]))
        return {row["id"]: index + 1 for index, row in enumerate(rows)}

    def with_payer_name(self, ticket: dict[str, Any], display_ids: dict[str, int] | None = None) -> dict[str, Any]:
        row = ticket.copy()
        row.setdefault("tag_ids", [])
        row["category"] = row.get("category") or "その他"
        user = self.get_user(row["payer_user_id"])
        row["payer_name"] = user["name"] if user else None
        row["display_id"] = (display_ids or self.ticket_display_ids()).get(row["id"], 0)
        return row

    @staticmethod
    def ticket_audit_dict(ticket: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": ticket["date"],
            "title": ticket["title"],
            "amount": ticket["amount"],
            "payer_user_id": ticket["payer_user_id"],
            "ratio_f": ticket["ratio_f"],
            "ratio_o": ticket["ratio_o"],
            "share_f": ticket["share_f"],
            "share_o": ticket["share_o"],
            "status": ticket["status"],
            "category": ticket.get("category", ""),
            "memo": ticket.get("memo", ""),
            "tag_ids": ticket.get("tag_ids", []),
        }

    def summarize(self, from_date: date, to_date: date, statuses: list[str], category: str | None = None, tag_id: str | None = None, tag_ids: list[str] | None = None) -> dict[str, Any]:
        tickets = self.list_tickets(from_date, to_date, statuses=statuses, category=category, tag_id=tag_id, tag_ids=tag_ids)
        users = {row["email"]: row for row in self.list_users()}
        user_f = users.get("f@example.com")
        user_o = users.get("o@example.com")
        paid_by_f = sum(t["amount"] for t in tickets if user_f and t["payer_user_id"] == user_f["id"])
        paid_by_o = sum(t["amount"] for t in tickets if user_o and t["payer_user_id"] == user_o["id"])
        share_f = sum(t["share_f"] for t in tickets)
        share_o = sum(t["share_o"] for t in tickets)
        balance_f = paid_by_f - share_f
        balance_o = paid_by_o - share_o
        if balance_f < 0:
            settlement = {"from_user": user_f["name"] if user_f else "User 1", "to_user": user_o["name"] if user_o else "User 2", "amount": abs(balance_f)}
        elif balance_o < 0:
            settlement = {"from_user": user_o["name"] if user_o else "User 2", "to_user": user_f["name"] if user_f else "User 1", "amount": abs(balance_o)}
        else:
            settlement = {"from_user": None, "to_user": None, "amount": 0}
        return {
            "from_": from_date,
            "to": to_date,
            "total_amount": sum(t["amount"] for t in tickets),
            "ticket_count": len(tickets),
            "paid_by_f": paid_by_f,
            "paid_by_o": paid_by_o,
            "share_f": share_f,
            "share_o": share_o,
            "balance_f": balance_f,
            "balance_o": balance_o,
            "settlement": settlement,
        }

    def write_audit(
        self,
        action: str,
        target_type: str,
        actor_user_id: UUID | str | None = None,
        target_id: UUID | str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        before = jsonable(before)
        after = jsonable(after)
        if before is not None and after is not None and before == after:
            return
        audit_id = str(uuid4())
        timestamp = now_iso()
        self._put("AUDIT", f"{timestamp}#{audit_id}", {
            "id": audit_id,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id) if target_id else None,
            "before": before,
            "after": after,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": timestamp,
        })

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        users = {row["id"]: row["name"] for row in self.list_users()}
        rows = sorted(self._items("AUDIT"), key=lambda row: row["created_at"], reverse=True)[: min(max(limit, 1), 300)]
        for row in rows:
            row["actor_name"] = users.get(row.get("actor_user_id"))
        return rows


store = DynamoStore()


def get_store() -> DynamoStore:
    return store
