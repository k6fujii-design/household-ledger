import unittest
from uuid import UUID

from app.routers.calendar import month, year
from app.routers.line_webhook import _draft_editor_html
import test_tags_memories as fixtures


class CalendarTagTest(unittest.TestCase):
    setUp = fixtures.TagsAndMemoriesTest.setUp
    ticket = fixtures.TagsAndMemoriesTest.ticket

    def test_calendar_tag_status_category_and_date_filters(self):
        for payload in [self.ticket(), self.ticket(amount=2000, category="交通費"),
                        self.ticket(status="canceled", amount=3000), self.ticket(tag_ids=[], amount=4000),
                        self.ticket(date="2026-08-01", amount=5000)]:
            self.store.create_ticket(payload, UUID(self.user["id"]))
        args = {"tag_id": self.tag["id"], "store": self.store, "user": self.user}
        result = month(2026, 7, statuses="new,settled", **args)
        self.assertEqual(result["days"][0]["total_amount"], 3000)
        self.assertEqual(result["days"][0]["ticket_count"], 2)
        self.assertEqual(month(2026, 7, statuses="canceled", **args)["days"][0]["total_amount"], 3000)
        self.assertEqual(month(2026, 7, category="食費", **args)["days"][0]["total_amount"], 1000)
        self.assertEqual(sum(r["total_amount"] for r in year(2026, **args)["months"]), 8000)
        self.assertEqual(month(2026, 7, tag_id="missing", store=self.store, user=self.user)["days"], [])

    def test_calendar_accepts_multiple_tags_as_or_filter(self):
        other_tag = self.store.save_tag("家族旅行")
        for payload in [self.ticket(amount=1000), self.ticket(amount=2000, tag_ids=[other_tag["id"]]), self.ticket(amount=3000, tag_ids=[])]:
            self.store.create_ticket(payload, UUID(self.user["id"]))

        result = month(2026, 7, tag_ids=f"{self.tag['id']},{other_tag['id']}", store=self.store, user=self.user)

        self.assertEqual(result["days"][0]["total_amount"], 3000)
        self.assertEqual(result["days"][0]["ticket_count"], 2)


class ReturnLinkTest(unittest.TestCase):
    def test_close_guidance_replaces_broken_return_button(self):
        for saved in (False, True):
            page = _draft_editor_html("test", {"payload": {}, "users": [], "categories": []}, saved=saved)
            self.assertNotIn("https://line.me/R/", page)
            self.assertIn("×（閉じる）", page)
            if saved:
                self.assertIn("まだチケットの登録は完了していません", page)
