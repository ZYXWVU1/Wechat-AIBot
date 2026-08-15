import tempfile
import unittest
from pathlib import Path

from windows_bridge.storage import BridgeStore


class BridgeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BridgeStore(Path(self.temp_dir.name) / "bridge.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_event_replay_and_deduplication(self):
        event = {
            "wechat_message_id": "message-1",
            "timestamp": 1,
            "type": 1,
            "is_text": True,
            "is_group": False,
            "at_me": False,
            "sender": "wxid_friend",
            "roomid": "",
            "receiver": "wxid_friend",
            "content": "你好",
        }
        event_id = self.store.append_event(event)
        self.assertEqual(event_id, 1)
        self.assertIsNone(self.store.append_event(event))
        events, latest = self.store.list_events(after=0, limit=100)
        self.assertEqual(latest, 1)
        self.assertEqual(events[0]["content"], "你好")

    def test_send_idempotency_record(self):
        self.store.record_send_result("request-1", "filehelper", "hello", 0)
        result = self.store.get_send_result("request-1")
        self.assertEqual(result["receiver"], "filehelper")
        self.assertEqual(result["content_hash"], self.store.content_hash("hello"))


if __name__ == "__main__":
    unittest.main()

