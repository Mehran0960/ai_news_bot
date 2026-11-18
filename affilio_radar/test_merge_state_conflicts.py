import unittest
from merge_state_conflicts import three_way_merge

class ThreeWayMergeTests(unittest.TestCase):
    def test_disjoint_video_destinations_survive(self):
        base={"published":{"p1":{"youtube_upload_status":"pending","filo_upload_status":"pending"}}}
        ours={"published":{"p1":{"youtube_upload_status":"uploaded","filo_upload_status":"pending"}}}
        theirs={"published":{"p1":{"youtube_upload_status":"pending","filo_upload_status":"submitted"}}}
        merged=three_way_merge(base,ours,theirs)
        self.assertEqual(merged["published"]["p1"]["youtube_upload_status"],"uploaded")
        self.assertEqual(merged["published"]["p1"]["filo_upload_status"],"submitted")

    def test_disjoint_photo_receipts_survive(self):
        base={"published":{"p1":{"delivery_status":{"telegram":"pending","bale":"pending"}}}}
        ours={"published":{"p1":{"delivery_status":{"telegram":"sent","bale":"pending"}}}}
        theirs={"published":{"p1":{"delivery_status":{"telegram":"pending","bale":"sent"}}}}
        self.assertEqual(three_way_merge(base,ours,theirs)["published"]["p1"]["delivery_status"],
                         {"telegram":"sent","bale":"sent"})

    def test_new_nested_destination_maps_merge_without_losing_siblings(self):
        base={"published":{"p1":{}}}
        ours={"published":{"p1":{"platform_message_ids":{"rubika":11}}}}
        theirs={"published":{"p1":{"platform_message_ids":{"eitaa":22}}}}
        merged=three_way_merge(base,ours,theirs)
        self.assertEqual(merged["published"]["p1"]["platform_message_ids"], {"rubika":11,"eitaa":22})

    def test_concurrent_editorial_channel_receipts_merge_into_one_event(self):
        base = {"editorial_delivery_history": [{
            "delivery_event_id": "editorial:guide:sequence:42",
            "content_id": "editorial:guide",
            "sequence_number": 42,
            "destinations": {},
        }]}
        ours = {"editorial_delivery_history": [{
            "delivery_event_id": "editorial:guide:sequence:42",
            "content_id": "editorial:guide",
            "sequence_number": 42,
            "destinations": {"telegram": {"status": "sent", "message_id": "tg-42"}},
        }]}
        theirs = {"editorial_delivery_history": [{
            "delivery_event_id": "editorial:guide:sequence:42",
            "content_id": "editorial:guide",
            "sequence_number": 42,
            "destinations": {"bale": {"status": "sent", "message_id": "ba-42"}},
        }]}
        merged = three_way_merge(base, ours, theirs)
        history = merged["editorial_delivery_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["destinations"], {
            "telegram": {"status": "sent", "message_id": "tg-42"},
            "bale": {"status": "sent", "message_id": "ba-42"},
        })

    def test_concurrent_editorial_ledger_rows_merge_by_fingerprint(self):
        base = {"editorial_content_ledger": [{
            "content_fingerprint": "fingerprint-1",
            "editorial_ids": ["guide"],
            "delivery_event_ids": [],
        }]}
        ours = {"editorial_content_ledger": [{
            "content_fingerprint": "fingerprint-1",
            "editorial_ids": ["guide"],
            "delivery_event_ids": ["event-a"],
        }]}
        theirs = {"editorial_content_ledger": [{
            "content_fingerprint": "fingerprint-1",
            "editorial_ids": ["guide"],
            "delivery_event_ids": ["event-b"],
        }]}
        merged = three_way_merge(base, ours, theirs)
        ledger = merged["editorial_content_ledger"]
        self.assertEqual(len(ledger), 1)
        self.assertEqual(set(ledger[0]["delivery_event_ids"]), {"event-a", "event-b"})

    def test_active_editorial_queue_survives_stale_concurrent_deletion(self):
        entry = {
            "content_id": "editorial:guide",
            "sequence_number": 42,
            "status": "partial",
            "platforms": {
                "telegram": {"status": "sent", "message_id": "tg-42"},
                "youtube": {"status": "pending"},
            },
        }
        base = {
            "editorial_delivery_queue": {"editorial:guide": entry},
            "editorial_delivery_attempts": [],
        }
        stale = {
            "editorial_delivery_queue": {},
            "editorial_delivery_attempts": [],
        }
        merged = three_way_merge(base, stale, base)
        self.assertIn("editorial:guide", merged["editorial_delivery_queue"])
        self.assertEqual(
            merged["editorial_delivery_queue"]["editorial:guide"]["platforms"]["telegram"]["message_id"],
            "tg-42",
        )

    def test_terminal_editorial_attempt_allows_queue_removal(self):
        entry = {
            "content_id": "editorial:guide",
            "sequence_number": 42,
            "status": "partial",
            "platforms": {"telegram": {"status": "sent"}},
        }
        base = {
            "editorial_delivery_queue": {"editorial:guide": entry},
            "editorial_delivery_attempts": [],
        }
        finalized = {
            "editorial_delivery_queue": {},
            "editorial_delivery_attempts": [{
                "content_id": "editorial:guide",
                "sequence_number": 42,
                "status": "completed",
            }],
        }
        merged = three_way_merge(base, finalized, base)
        self.assertNotIn("editorial:guide", merged["editorial_delivery_queue"])

    def test_latest_channel_timestamp_wins(self):
        base={"last_channel_published_at":"2026-11-17T10:00:00+00:00"}
        ours={"last_channel_published_at":"2026-11-17T10:05:00+00:00"}
        theirs={"last_channel_published_at":"2026-11-17T10:06:00+00:00"}
        self.assertEqual(three_way_merge(base,ours,theirs)["last_channel_published_at"],theirs["last_channel_published_at"])

if __name__ == "__main__": unittest.main()
