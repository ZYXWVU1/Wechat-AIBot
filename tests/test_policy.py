import unittest
from types import SimpleNamespace

from nas_backend.app.policy import decide


def settings(**overrides):
    values = {
        "auto_reply_enabled": True,
        "direct_reply_enabled": True,
        "group_reply_enabled": True,
        "allowed_direct_senders": frozenset({"wxid_friend"}),
        "allowed_groups": frozenset({"group@chatroom"}),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PolicyTests(unittest.TestCase):
    def test_group_requires_allowlist_and_mention(self):
        event = {
            "type": 1,
            "is_text": True,
            "is_group": True,
            "at_me": False,
            "roomid": "group@chatroom",
            "sender": "wxid_friend",
            "receiver": "group@chatroom",
            "content": "hello",
        }
        self.assertEqual(decide(event, settings()).reason, "not_mentioned")
        event["at_me"] = True
        self.assertTrue(decide(event, settings()).should_reply)

    def test_direct_sender_requires_allowlist(self):
        event = {
            "type": 1,
            "is_text": True,
            "is_group": False,
            "at_me": False,
            "roomid": "",
            "sender": "unknown",
            "receiver": "unknown",
            "content": "hello",
        }
        decision = decide(event, settings())
        self.assertFalse(decision.should_reply)
        self.assertEqual(decision.reason, "sender_not_allowed")

    def test_global_switch_wins(self):
        event = {
            "type": 1,
            "is_text": True,
            "is_group": False,
            "sender": "wxid_friend",
            "receiver": "wxid_friend",
            "content": "hello",
        }
        self.assertEqual(
            decide(event, settings(auto_reply_enabled=False)).reason,
            "auto_reply_disabled",
        )


if __name__ == "__main__":
    unittest.main()

