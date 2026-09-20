import json
import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from app.core.config import settings
from app.schemas.ticket import TicketCreate
from app.services.agent_preferences import preference_command, resolve_tag_ids, patch_tag_ids
from app.services.line_agent import (
    _apply_create_candidate_changes, _maybe_answer_summary, _ticket_payload_dict,
    _ticket_payload_from_dict, _try_bedrock_intent, handle_line_text,
    get_ticket_draft_editor, update_ticket_draft_from_editor,
)
from app.routers.line_webhook import _draft_editor_html
from app.store import DynamoStore, jsonable


class MemoryStore(DynamoStore):
    def __init__(self):
        self.rows = {}

    def _put(self, kind, item_id, item):
        row = jsonable(deepcopy(item))
        self.rows[kind, str(item_id)] = row
        return deepcopy(row)

    def _get(self, kind, item_id):
        return deepcopy(self.rows.get((kind, str(item_id))))

    def _items(self, kind):
        return [deepcopy(row) for (key, _), row in self.rows.items() if key == kind]

    def _delete(self, kind, item_id):
        self.rows.pop((kind, str(item_id)), None)


class TagsAndMemoriesTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.user = {"id": str(uuid4()), "name": "A", "email": "f@example.com"}
        self.other = {"id": str(uuid4()), "name": "B", "email": "o@example.com"}
        for user in (self.user, self.other):
            self.store._put("USER", user["id"], user)
        self.tag = self.store.save_tag("＃北海道旅行")

    def ticket(self, **changes):
        return TicketCreate(**{
            "date": "2026-07-31", "title": "旅行", "amount": 1000,
            "payer_user_id": self.user["id"], "ratio_f": 3, "ratio_o": 7,
            "status": "new", "category": "食費", "memo": "", "tag_ids": [self.tag["id"]],
            **changes,
        })

    def test_creation_category_proposals(self):
        from app.services.line_agent import _propose_create_category
        for name in ("食費", "日用品", "ペット用品"):
            self.store._put("CATEGORY", name, {"name": name})
        cases = [
            ("サミットで魚かって3000円", {}, "食費"),
            ("スーパーで洗剤800円", {"category": "日用品"}, "日用品"),
            ("犬のおもちゃ1000円", {"category": "ペット用品"}, "ペット用品"),
            ("魚3000円 カテゴリは未指定", {"category": "食費"}, ""),
            ("魚3000円", {"category": "存在しない分類"}, "食費"),
            ("1000円", {"category": "存在しない分類"}, ""),
            ("魚3000円 カテゴリは日用品", {"category": "食費"}, "日用品"),
        ]
        for text, ai, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_propose_create_category(text, ai, self.store)[0], expected)

    def test_bedrock_receives_original_purchase_when_asking_amount(self):
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": '{"intent":"create_ticket","category":"食費"}'}]}}}
        pending = {"intent": "create_ticket", "text": "サミットで魚を買った"}
        with patch.object(settings, "line_agent_mode", "bedrock"), patch("app.services.line_agent.boto3.client", return_value=client):
            _try_bedrock_intent("3000円", ["食費"], pending=pending)
        data = json.loads(client.converse.call_args.kwargs["messages"][0]["content"][0]["text"])
        self.assertEqual(data["current_operation"]["text"], pending["text"])

    def test_cross_month_category_summary_counts_each_ticket_once(self):
        for payload in [self.ticket(), self.ticket(date="2026-08-01", category="交通費", amount=2000, status="settled"), self.ticket(status="canceled"), self.ticket(tag_ids=[])]:
            self.store.create_ticket(payload, UUID(self.user["id"]))
        summary = self.store.summarize(date.min, date.max, ["new", "settled"], tag_id=self.tag["id"])
        self.assertEqual((summary["total_amount"], summary["ticket_count"]), (3000, 2))
        filtered = self.store.summarize(date.min, date.max, ["new", "settled"], category="食費", tag_id=self.tag["id"])
        self.assertEqual(filtered["total_amount"], 1000)

    def test_tag_rename_preserves_links_and_used_delete_is_rejected(self):
        self.store.create_ticket(self.ticket(), UUID(self.user["id"]))
        renamed = self.store.save_tag("札幌旅行", self.tag["id"])
        self.assertEqual(renamed["id"], self.tag["id"])
        self.assertEqual(len(self.store.list_tickets(tag_id=renamed["id"])), 1)
        with self.assertRaises(ValueError):
            self.store.delete_tag(renamed["id"])

    def test_unknown_tag_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_ticket(self.ticket(tag_ids=[uuid4()]), UUID(self.user["id"]))
        with self.assertRaises(ValueError):
            resolve_tag_ids("", {"tag_names": ["未登録"]}, self.store)

    def test_payload_roundtrip_and_date_change_preserve_tags(self):
        payload = self.ticket()
        serialized = _ticket_payload_dict(payload)
        self.assertEqual(_ticket_payload_from_dict(serialized).tag_ids, payload.tag_ids)
        after, _, _ = _apply_create_candidate_changes(serialized, "日付を2026-08-02にして", self.user, self.store, {"tag_names": [], "amount": 9999})
        self.assertEqual(after.tag_ids, payload.tag_ids)
        self.assertEqual(after.amount, payload.amount)

    def test_tag_change_does_not_modify_other_fields(self):
        after, _, _ = _apply_create_candidate_changes(_ticket_payload_dict(self.ticket()), "タグを全部外して", self.user, self.store, {"tag_names": [], "amount": 999, "ratio_f": 9, "ratio_o": 1})
        self.assertEqual(after.tag_ids, [])
        self.assertEqual((after.amount, after.ratio_f, after.ratio_o), (1000, 3, 7))

    def test_add_remove_tag_preserves_other_tags(self):
        other_tag = self.store.save_tag("家族旅行")
        both = patch_tag_ids([self.tag["id"]], "タグを追加", {"tag_names": ["家族旅行"], "tag_operation": "add"}, self.store)
        self.assertEqual(both, [self.tag["id"], other_tag["id"]])
        remaining = patch_tag_ids(both, "タグを外して", {"tag_names": ["北海道旅行"], "tag_operation": "remove"}, self.store)
        self.assertEqual(remaining, [other_tag["id"]])

    def test_tag_commands_rename_delete(self):
        preference_command("タグ名変更", {"intent": "rename_tag", "tag_name": "北海道旅行", "new_tag_name": "札幌旅行"}, self.user, self.store)
        self.assertEqual(self.store.list_tags()[0]["name"], "札幌旅行")
        preference_command("タグを削除", {"intent": "delete_tag", "tag_name": "札幌旅行"}, self.user, self.store)
        self.assertEqual(self.store.list_tags(), [])

    def test_memories_are_user_scoped_and_survive_session_clear(self):
        row = self.store.save_memory(self.user["id"], "件名を短くして")
        self.assertEqual(self.store.list_memories(self.other["id"]), [])
        self.store.delete_memory(self.other["id"], row["id"])
        handle_line_text("やめる", "test-line-user", self.user, self.store)
        self.assertEqual(len(self.store.list_memories(self.user["id"])), 1)
        self.store.delete_memory(self.user["id"], row["id"])
        self.assertEqual(self.store.list_memories(self.user["id"]), [])

    def test_memory_requires_explicit_request_and_deduplicates(self):
        ai = {"intent": "remember", "memory_content": "件名を短くして"}
        self.assertIsNone(preference_command("スーパーで買い物した", ai, self.user, self.store))
        for _ in range(2):
            self.assertIn("覚えました", preference_command("件名を短くするよう覚えて", ai, self.user, self.store))
        self.assertEqual(len(self.store.list_memories(self.user["id"])), 1)

    def test_memory_limits(self):
        with self.assertRaises(ValueError):
            self.store.save_memory(self.user["id"], "x" * 501)
        for i in range(30):
            self.store.save_memory(self.user["id"], str(i))
        with self.assertRaises(ValueError):
            self.store.save_memory(self.user["id"], "31")

    def test_bedrock_receives_preferences_as_data_with_system_constraints(self):
        memory = self.store.save_memory(self.user["id"], "件名を短くして")
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": '{"intent":"chat"}'}]}}}
        with patch.object(settings, "line_agent_mode", "bedrock"), patch("app.services.line_agent.boto3.client", return_value=client):
            result = _try_bedrock_intent("こんにちは", [], [memory], [self.tag])
        self.assertEqual(result["intent"], "chat")
        args = client.converse.call_args.kwargs
        data = json.loads(args["messages"][0]["content"][0]["text"])
        self.assertEqual(data["saved_preferences"][0]["content"], "件名を短くして")
        self.assertIn("確認必須", args["system"][0]["text"])

    def test_line_tag_summary_all_time(self):
        self.store.create_ticket(self.ticket(), UUID(self.user["id"]))
        reply = _maybe_answer_summary("北海道旅行の合計は？", self.user, self.store, {"intent": "summary", "tag_names": ["北海道旅行"], "all_time": True})
        self.assertIn("全期間", reply.reply)
        self.assertIn("1,000円", reply.reply)

    def test_line_create_tag_and_ticket_confirmation(self):
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "create_tag", "tag_name": "家族旅行"}):
            reply = handle_line_text("家族旅行というタグを作成して", "test-line-user", self.user, self.store)
        self.assertIn("家族旅行", reply.reply)
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "create_ticket", "tag_names": ["北海道旅行"], "title": "昼食"}):
            reply = handle_line_text("今日1000円 昼食 #北海道旅行", "test-line-user", self.user, self.store)
        self.assertIn("#北海道旅行", reply.reply)
        self.assertIn("登録する", reply.quick_replies)
        self.assertEqual(self.store.list_tickets(), [])
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "create_ticket"}):
            handle_line_text("登録する", "test-line-user", self.user, self.store)
        self.assertEqual(self.store.list_tickets()[0]["tag_ids"], [self.tag["id"]])

    def test_editor_tags_survive_save_and_render(self):
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "create_ticket", "tag_names": ["北海道旅行"]}):
            handle_line_text("今日1000円 昼食 #北海道旅行", "test-line-user", self.user, self.store, public_base_url="http://localhost:8000")
        token = next(item_id for kind, item_id in self.store.rows if kind == "AGENT_DRAFT_LINK")
        editor = get_ticket_draft_editor(self.store, token)
        page = _draft_editor_html(token, editor)
        self.assertIn("min-width: 0; max-width: 100%", page)
        self.assertIn("input[type=date] { appearance: none; -webkit-appearance: none;", page)
        self.assertIn(f'value="{self.tag["id"]}" checked', page)
        values = {**editor["payload"], "date": "2026-08-02"}
        payload, context = update_ticket_draft_from_editor(self.store, token, values)
        self.assertEqual(payload.tag_ids, [UUID(self.tag["id"])])
        self.assertEqual(context["tags"][0]["id"], self.tag["id"])
        values["tag_ids"] = [str(uuid4())]
        with self.assertRaises(ValueError):
            update_ticket_draft_from_editor(self.store, token, values)

    def test_named_update_search_select_edit_and_confirm(self):
        wanted = self.store.create_ticket(self.ticket(date="2026-09-19", title="カマス", amount=1000), UUID(self.user["id"]))
        self.store.create_ticket(self.ticket(date="2026-09-20", title="カマス", amount=2000), UUID(self.user["id"]))
        self.store.create_ticket(self.ticket(date="2026-09-19", title="昼食", amount=3000), UUID(self.user["id"]))
        ai = {"intent": "update_ticket", "target": {"title": "カマス", "date": "2026-09-19"}}
        with patch("app.services.line_agent._try_bedrock_intent", return_value=ai):
            reply = handle_line_text("昨日のカマスのチケット更新したい", "line", self.user, self.store)
        self.assertIn("選んで", reply.reply)
        self.assertNotIn("2,000", reply.reply)
        self.assertNotIn("昼食", reply.reply)
        reply = handle_line_text("選択 1", "line", self.user, self.store)
        self.assertIn("どの項目", reply.reply)
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "update_ticket", "amount": 1800}):
            reply = handle_line_text("金額を1800円にして", "line", self.user, self.store)
        self.assertEqual(self.store.get_ticket(UUID(wanted["id"]))["amount"], 1000)
        self.assertIn("更新する", reply.quick_replies)
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "unknown"}):
            handle_line_text("更新する", "line", self.user, self.store)
        actual = self.store.get_ticket(UUID(wanted["id"]))
        self.assertEqual((actual["amount"], actual["date"], actual["ratio_f"]), (1800, "2026-09-19", 3))

    def test_policy_without_remember_word_proposes_then_persists(self):
        ai = {"intent": "remember", "memory_content": "回答は簡潔にする"}
        with patch("app.services.line_agent._try_bedrock_intent", return_value=ai):
            reply = handle_line_text("回答は簡潔にしてください", "line", self.user, self.store)
        self.assertEqual(self.store.list_memories(self.user["id"]), [])
        self.assertIn("この方針を保存", reply.quick_replies)
        reply = handle_line_text("この方針を保存", "line", self.user, self.store)
        self.assertIn("覚えました", reply.reply)
        self.assertEqual(self.store.list_memories(self.user["id"])[0]["content"], "回答は簡潔にする")

    def test_policy_rejected_does_not_persist(self):
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "remember", "memory_content": "簡潔に回答"}):
            handle_line_text("簡潔に回答してください", "line", self.user, self.store)
        reply = handle_line_text("保存しない", "line", self.user, self.store)
        self.assertIn("保存していません", reply.reply)
        self.assertEqual(self.store.list_memories(self.user["id"]), [])

    def test_short_fullwidth_expense_overrides_chat_or_unknown(self):
        for intent in ("chat", "unknown"):
            with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": intent}):
                reply = handle_line_text("サミットで魚かって３０００円", intent, self.user, self.store)
            self.assertIn("3,000円", reply.reply)
            self.assertIn("登録する", reply.quick_replies)
            self.assertNotIn("処理ログ", reply.reply)
        self.assertEqual(self.store.list_tickets(), [])

    def test_short_purchase_asks_for_missing_amount(self):
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "chat"}):
            reply = handle_line_text("サミットで魚かってきた", "line", self.user, self.store)
        self.assertIn("金額", reply.reply)
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "unknown"}):
            reply = handle_line_text("３０００円", "line", self.user, self.store)
        self.assertIn("登録する", reply.quick_replies)

    def test_question_and_negative_not_forced_to_creation(self):
        for text in ("3000円で買いたいけどどう？", "3000円は登録しないで", "先月の合計は3000円ですか"):
            with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "unknown"}):
                reply = handle_line_text(text, "line", self.user, self.store)
            self.assertNotIn("登録する", reply.quick_replies)

    def test_shared_memory_visible_to_both_personal_isolated(self):
        shared = self.store.save_memory(self.user["id"], "共通方針", "shared")
        personal = self.store.save_memory(self.user["id"], "本人だけ")
        self.assertEqual(self.store.list_memories(self.other["id"], "shared")[0]["id"], shared["id"])
        self.assertEqual(self.store.list_memories(self.other["id"]), [])
        self.store.delete_memory(self.other["id"], personal["id"], "shared")
        self.assertEqual(len(self.store.list_memories(self.user["id"])), 1)
        self.store.delete_memory(self.other["id"], shared["id"], "shared")
        self.assertEqual(self.store.list_memories(self.user["id"], "shared"), [])

    def test_agent_receives_shared_and_only_senders_personal_memories(self):
        self.store.save_memory(self.user["id"], "共通", "shared")
        self.store.save_memory(self.user["id"], "A専用")
        self.store.save_memory(self.other["id"], "B専用")
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "chat"}) as model:
            handle_line_text("こんにちは", "line", self.user, self.store)
        self.assertEqual([r["content"] for r in model.call_args.args[2]], ["共通", "A専用"])

    def test_line_shared_memory_save_and_delete(self):
        reply = preference_command("共通で覚えて", {"intent": "remember", "memory_content": "店名を入れる"}, self.user, self.store)
        self.assertIn("共通", reply)
        row = self.store.list_memories(self.other["id"], "shared")[0]
        preference_command("共通の注意事項を忘れて", {"intent": "forget_memory", "memory_id": row["id"]}, self.other, self.store)
        self.assertEqual(self.store.list_memories(self.user["id"], "shared"), [])

    def test_shared_proposal_confirmation_keeps_scope(self):
        with patch("app.services.line_agent._try_bedrock_intent", return_value={"intent": "remember", "memory_content": "回答を短くする"}):
            reply = handle_line_text("二人共通で回答を短くしてください", "line", self.user, self.store)
        self.assertIn("共通", reply.reply)
        self.assertEqual(self.store.list_memories(self.other["id"], "shared"), [])
        handle_line_text("この方針を保存", "line", self.user, self.store)
        self.assertEqual(self.store.list_memories(self.other["id"], "shared")[0]["content"], "回答を短くする")
        self.assertEqual(self.store.list_memories(self.user["id"]), [])

    def test_existing_personal_memories_need_no_migration(self):
        memory_id = str(uuid4())
        self.store._put(f"AGENT_MEMORY#{self.user['id']}", memory_id, {"id": memory_id, "content": "旧データ", "created_at": "2026-01-01"})
        row = self.store.list_memories(self.user["id"])[0]
        self.assertEqual((row["content"], row["scope"]), ("旧データ", "personal"))
        self.assertEqual(self.store.list_memories(self.other["id"]), [])

    def test_trace_not_in_line_even_when_old_setting_is_enabled(self):
        from app.services.line_agent import _format_trace
        with patch.object(settings, "line_agent_trace_enabled", True):
            self.assertEqual(_format_trace(["create_ticketを実行"]), "")
