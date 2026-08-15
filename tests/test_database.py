import tempfile
import time
import unittest
from pathlib import Path

from nas_backend.app.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "bot.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cursor_and_inbound_deduplication(self):
        event = {
            "event_id": 1,
            "wechat_message_id": "msg-1",
            "sender": "wxid_friend",
            "receiver": "wxid_friend",
            "content": "hello",
            "timestamp": 1,
        }
        self.assertTrue(self.database.add_inbound(event, "wxid_friend"))
        self.assertFalse(self.database.add_inbound(event, "wxid_friend"))
        self.database.set_cursor(9)
        self.assertEqual(self.database.get_cursor(), 9)

    def test_outbox_claim_and_complete(self):
        item_id = self.database.enqueue(
            "conversation", "filehelper", "hello", "", time.time() - 1
        )
        claimed = self.database.claim_due()
        self.assertEqual(claimed["id"], item_id)
        self.database.mark_sent(item_id)
        self.assertIsNone(self.database.claim_due())


if __name__ == "__main__":
    unittest.main()

