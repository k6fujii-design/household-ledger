import unittest
from unittest.mock import Mock, patch

from app.core.config import settings
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services.line_agent import (
    _apply_create_candidate_changes, _parse_ratio_change,
    _ticket_payload_dict, _try_bedrock_intent, handle_line_text,
)
import test_tags_memories as fixtures


class AgentRegressionTest(unittest.TestCase):
    setUp = fixtures.TagsAndMemoriesTest.setUp
    ticket = fixtures.TagsAndMemoriesTest.ticket

    def test_named_ratios_override_invalid_ai(self):
        for text in ("ユーザ1 3、ユーザ2 7", "ユーザー１ ３、ユーザー２ ７", "User2 7 User1 3", "A 3 B 7", "3:7", "30%:70%"):
            with self.subTest(text=text):
                actual = _parse_ratio_change(text, self.store, {"ratio_f": 9, "ratio_o": 14}, self.user)
                self.assertEqual(actual[:2], (3, 7))

    def test_dates_and_invalid_ai_are_not_ratios(self):
        for text in ("9/20", "2026-09-20", "12:30"):
            self.assertEqual(_parse_ratio_change(text, self.store, {"ratio_f": 9, "ratio_o": 14})[:2], (None, None))
        for f, o in ((float("nan"), 5), (-1, 11), (0, 0), (True, 9)):
            self.assertEqual(_parse_ratio_change("", self.store, {"ratio_f": f, "ratio_o": o})[:2], (None, None))

    def test_rounding_keeps_total_ten(self):
        self.assertEqual(_parse_ratio_change("", self.store, {"ratio_f": 25, "ratio_o": 75})[:2], (2, 8))
        self.assertEqual(_parse_ratio_change("", self.store, {"ratio_f": 0, "ratio_o": 10})[:2], (0, 10))

    def test_invalid_ratios_rejected_by_write_schemas(self):
        values = self.ticket().model_dump()
        for schema in (TicketCreate, TicketUpdate):
            with self.assertRaises(ValueError):
                schema(**{**values, "ratio_f": 9, "ratio_o": 14})

    def test_named_ratio_edit_preserves_other_fields(self):
        before = self.ticket(payer_user_id=self.other["id"])
        after, _, changed = _apply_create_candidate_changes(
            _ticket_payload_dict(before), "A 4、B 6", self.user, self.store,
            {"ratio_f": 9, "ratio_o": 14, "amount": 9999},
        )
        self.assertTrue(changed)
        self.assertEqual((after.ratio_f, after.ratio_o), (4, 6))
        self.assertEqual((after.payer_user_id, after.amount, after.date), (before.payer_user_id, before.amount, before.date))

    def test_summary_and_friendly_comment_survive_confirmation(self):
        initial = {"intent": "chat"}
        repaired = {"intent": "create_ticket", "title": "サミットの魚", "friendly_comment": "お魚買ってきたんだね！", "amount": 9999, "ratio_f": 9, "ratio_o": 14}
        with patch.object(settings, "line_agent_mode", "bedrock"), patch("app.services.line_agent._try_bedrock_intent", side_effect=[initial, repaired]) as parse:
            reply = handle_line_text("サミットで魚かって3000円", "line", self.user, self.store)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(reply.preface, repaired["friendly_comment"])
        self.assertIn("サミットの魚", reply.reply)
        self.assertIn("3,000円", reply.reply)
        self.assertIn("50% / 50%", reply.reply)
        self.assertEqual(self.store.list_tickets(), [])

    def test_bedrock_failure_does_not_silently_use_rules(self):
        with patch.object(settings, "line_agent_mode", "bedrock"), patch("app.services.line_agent._try_bedrock_intent", return_value=None):
            reply = handle_line_text("魚3000円", "line", self.user, self.store)
        self.assertIn("読み取りに失敗", reply.reply)
        self.assertEqual(self.store.list_tickets(), [])

    def test_bedrock_text_blocks_after_nontext_block(self):
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"reasoningContent": {}}, {"text": '{"intent":"create_ticket",'}, {"text": '"title":"魚"}'}]}}}
        with patch.object(settings, "line_agent_mode", "bedrock"), patch("app.services.line_agent.boto3.client", return_value=client):
            result = _try_bedrock_intent("魚3000円", [])
        self.assertEqual(result["title"], "魚")

    def test_invalid_ai_ratio_asks_without_creating(self):
        ai = {"intent": "create_ticket", "title": "魚", "friendly_comment": "魚買ったんだね！", "ratio_f": 9, "ratio_o": 14}
        with patch("app.services.line_agent._try_bedrock_intent", return_value=ai):
            reply = handle_line_text("魚3000円 負担比率を設定して", "line", self.user, self.store)
        self.assertIn("負担比率を正しく読み取れません", reply.reply)
        self.assertEqual(self.store.list_tickets(), [])
