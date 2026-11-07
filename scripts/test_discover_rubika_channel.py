import unittest

from discover_rubika_channel import (
    extract_chat_ids,
    is_target_channel,
    normalize_username,
)


class RubikaChannelDiscoveryTests(unittest.TestCase):
    def test_normalizes_optional_at_prefix_and_case(self):
        self.assertEqual(normalize_username(" @OfferChin "), "offerchin")

    def test_extracts_unique_chat_ids_only(self):
        updates = [
            {"type": "NewMessage", "chat_id": "c1", "new_message": {"text": "private text"}},
            {"type": "NewMessage", "chat_id": "c1", "new_message": {"text": "another"}},
            {"type": "EventData", "chat_id": "c2"},
            {"type": "NewMessage", "new_message": {"text": "no chat id"}},
            None,
        ]
        self.assertEqual(extract_chat_ids(updates), ["c1", "c2"])

    def test_matches_target_channel_by_username(self):
        self.assertTrue(is_target_channel(
            {"chat_type": "Channel", "username": "offerchin", "title": "آفرچین"},
            "@OfferChin",
        ))

    def test_rejects_title_only_match_when_username_missing(self):
        self.assertFalse(is_target_channel(
            {"chat_type": "Channel", "title": "OfferChin"},
            "offerchin",
        ))

    def test_rejects_private_chat_with_same_title(self):
        self.assertFalse(is_target_channel(
            {"chat_type": "User", "username": "offerchin", "title": "OfferChin"},
            "offerchin",
        ))

    def test_rejects_similar_but_not_exact_username(self):
        self.assertFalse(is_target_channel(
            {"chat_type": "Channel", "username": "offerchin_news", "title": "Other"},
            "offerchin",
        ))


if __name__ == "__main__":
    unittest.main()
