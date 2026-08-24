from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wsa.outreach import (
    CREATE_CONFIRMATION_TEXT,
    UPDATE_CONFIRMATION_TEXT,
    create_outreach_drafts,
    list_outreach_drafts,
    update_outreach_draft,
)
from wsa.store import init_db


class OutreachDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db = Path(self.tmp.name) / "social.db"
        init_db(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create(self, **kwargs) -> list:
        params = {
            "items": [{"person_name": "王志平", "draft_text": "Kiwi 新版上线了，想你用得上。"}],
            "campaign": "kiwi-release",
            "topic": "Kiwi 新版上线通知",
            "confirmed": True,
            "confirmation_text": CREATE_CONFIRMATION_TEXT,
        }
        params.update(kwargs)
        return create_outreach_drafts(self.db, **params)

    def test_create_requires_explicit_confirmation(self):
        with self.assertRaises(ValueError):
            create_outreach_drafts(self.db, items=[{"person_name": "王志平", "draft_text": "hi"}])
        with self.assertRaises(ValueError):
            create_outreach_drafts(
                self.db,
                items=[{"person_name": "王志平", "draft_text": "hi"}],
                confirmed=True,
                confirmation_text="wrong text",
            )

    def test_create_list_and_status_lifecycle(self):
        created = self._create(
            items=[
                {"person_name": "王志平", "draft_text": "Kiwi 新版上线了。"},
                {"person_name": "刘继红", "draft_text": "Kiwi 新版上线了。", "send_mode": "computer_use"},
            ]
        )
        self.assertEqual(2, len(created))
        self.assertEqual({"draft"}, {draft.status for draft in created})
        self.assertEqual("computer_use", created[1].send_mode)

        drafts = list_outreach_drafts(self.db, status="draft")
        self.assertEqual(2, len(drafts))

        approved = update_outreach_draft(
            self.db,
            draft_id=created[0].id,
            action="approve",
            confirmed=True,
            confirmation_text=UPDATE_CONFIRMATION_TEXT,
        )
        self.assertEqual("approved", approved.status)
        self.assertEqual([created[0].id], [d.id for d in list_outreach_drafts(self.db, status="approved")])
        self.assertEqual([created[0].id], [d.id for d in list_outreach_drafts(self.db, campaign="kiwi-release", status="approved")])

        sent = update_outreach_draft(
            self.db,
            draft_id=created[0].id,
            action="mark_sent",
            confirmed=True,
            confirmation_text=UPDATE_CONFIRMATION_TEXT,
        )
        self.assertEqual("sent", sent.status)

        edited = update_outreach_draft(
            self.db,
            draft_id=created[1].id,
            action="edit",
            draft_text="改过的草稿",
            confirmed=True,
            confirmation_text=UPDATE_CONFIRMATION_TEXT,
        )
        self.assertEqual("改过的草稿", edited.draft_text)
        self.assertEqual("draft", edited.status)

    def test_update_requires_confirmation_and_valid_ids(self):
        created = self._create()
        with self.assertRaises(ValueError):
            update_outreach_draft(self.db, draft_id=created[0].id, action="approve")
        with self.assertRaises(ValueError):
            update_outreach_draft(
                self.db, draft_id=created[0].id, action="approve",
                confirmed=True, confirmation_text="wrong",
            )
        with self.assertRaises(ValueError):
            update_outreach_draft(
                self.db, draft_id=999, action="approve",
                confirmed=True, confirmation_text=UPDATE_CONFIRMATION_TEXT,
            )
        with self.assertRaises(ValueError):
            update_outreach_draft(
                self.db, draft_id=created[0].id, action="send_now",
                confirmed=True, confirmation_text=UPDATE_CONFIRMATION_TEXT,
            )

    def test_create_validates_items(self):
        with self.assertRaises(ValueError):
            self._create(items=[])
        with self.assertRaises(ValueError):
            self._create(items=[{"person_name": "", "draft_text": "hi"}])
        with self.assertRaises(ValueError):
            self._create(items=[{"person_name": "王志平", "draft_text": "hi", "send_mode": "auto"}])


if __name__ == "__main__":
    unittest.main()
