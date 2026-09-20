import unittest
from uuid import UUID

from app.routers.line_webhook import _draft_editor_html
from app.services.line_agent import _apply_create_candidate_changes


USER_1_ID = "11111111-1111-1111-1111-111111111111"
USER_2_ID = "22222222-2222-2222-2222-222222222222"


class FakeStore:
    def list_categories(self):
        return [{"name": "食費"}, {"name": "娯楽"}]

    def list_users(self):
        return [
            {"id": USER_1_ID, "email": "f@example.com", "name": "User 1"},
            {"id": USER_2_ID, "email": "o@example.com", "name": "User 2"},
        ]


class CreateCandidateChangesTest(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.user = {"id": USER_1_ID, "email": "f@example.com", "name": "User 1"}
        self.pending = {
            "date": "2026-09-19",
            "title": "マリオカート",
            "amount": 8980,
            "payer_user_id": USER_1_ID,
            "ratio_f": 5,
            "ratio_o": 5,
            "status": "new",
            "category": "娯楽",
            "memo": "LINEから登録",
        }

    def test_date_change_does_not_change_amount_or_ratio(self):
        ai = {
            "intent": "create_ticket",
            "date": "2026-09-20",
            "amount": 1200,
            "ratio_f": 7,
            "ratio_o": 3,
        }

        payload, _, changed = _apply_create_candidate_changes(
            self.pending,
            "日付を2026-09-20にして",
            self.user,
            self.store,
            ai,
        )

        self.assertTrue(changed)
        self.assertEqual(payload.date.isoformat(), "2026-09-20")
        self.assertEqual(payload.amount, 8980)
        self.assertEqual((payload.ratio_f, payload.ratio_o), (5, 5))

    def test_ratio_change_does_not_change_amount(self):
        ai = {
            "intent": "create_ticket",
            "amount": 1200,
            "ratio_f": 7,
            "ratio_o": 3,
        }

        payload, _, changed = _apply_create_candidate_changes(
            self.pending,
            "負担比率を7:3にして",
            self.user,
            self.store,
            ai,
        )

        self.assertTrue(changed)
        self.assertEqual(payload.amount, 8980)
        self.assertEqual((payload.ratio_f, payload.ratio_o), (7, 3))
        self.assertEqual(payload.payer_user_id, UUID(USER_1_ID))


class DraftEditorHtmlTest(unittest.TestCase):
    def test_editor_contains_typed_controls(self):
        editor = {
            "payload": {
                "date": "2026-09-19",
                "title": "Game",
                "amount": 8980,
                "payer_user_id": USER_1_ID,
                "ratio_f": 5,
                "ratio_o": 5,
                "status": "new",
                "category": "Entertainment",
                "memo": "",
            },
            "users": [
                {"id": USER_1_ID, "email": "f@example.com", "name": "User 1"},
                {"id": USER_2_ID, "email": "o@example.com", "name": "User 2"},
            ],
            "categories": [{"name": "Entertainment"}, {"name": "Food"}],
        }

        page = _draft_editor_html("test-token", editor)

        self.assertIn('type="date"', page)
        self.assertIn('type="number"', page)
        self.assertIn('type="range"', page)
        self.assertIn('<select name="category">', page)
        self.assertIn('<select name="payer_user_id"', page)


if __name__ == "__main__":
    unittest.main()
