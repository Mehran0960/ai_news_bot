import unittest

from merge_video_destination_state import merge_destination_snapshot


def state_base():
    return {
        "published": {
            "dkp-100": {
                "content_type": "product",
                "youtube_upload_status": "pending",
                "aparat_upload_status": "pending",
                "filo_upload_status": "pending",
                "video_generation_status": "pending",
            }
        },
        "editorial_delivery_queue": {
            "editorial:delivery-guide": {
                "content_id": "editorial:delivery-guide",
                "status": "partial",
                "platforms": {
                    "youtube": {"status": "pending"},
                    "aparat": {"status": "pending"},
                    "filo": {"status": "pending"},
                },
            }
        },
        "editorial_delivery_history": [],
        "editorial_cycle": {"used_ids": [], "cycle_number": 1},
    }


class MergeVideoDestinationStateTests(unittest.TestCase):
    def test_destination_merge_does_not_overwrite_other_video_destinations(self):
        base = state_base()
        source = {
            **base,
            "published": {
                "dkp-100": {
                    **base["published"]["dkp-100"],
                    "filo_upload_status": "published",
                    "filo_video_url": "https://ifilo.net/v/abc",
                }
            },
            "filo_login_verification_status": "verified",
        }
        target = state_base()
        target["published"]["dkp-100"]["youtube_upload_status"] = "uploaded"
        target["published"]["dkp-100"]["youtube_video_url"] = "https://youtube.com/shorts/xyz"
        result = merge_destination_snapshot(target, base, source, "filo")
        row = target["published"]["dkp-100"]
        self.assertEqual(row["filo_upload_status"], "published")
        self.assertEqual(row["youtube_upload_status"], "uploaded")
        self.assertEqual(row["youtube_video_url"], "https://youtube.com/shorts/xyz")
        self.assertEqual(target["filo_login_verification_status"], "verified")
        self.assertEqual(result["destination"], "filo")

    def test_successful_video_generation_cannot_be_regressed_by_another_worker(self):
        base = state_base()
        source = {
            **base,
            "published": {
                "dkp-100": {
                    **base["published"]["dkp-100"],
                    "video_generation_status": "pending",
                    "filo_upload_status": "retry",
                }
            },
        }
        target = state_base()
        target["published"]["dkp-100"].update({
            "video_generation_status": "generated",
            "video_file_name": "product-100.mp4",
            "video_generated_at": "2026-11-17T18:00:00+00:00",
        })
        merge_destination_snapshot(target, base, source, "filo")
        row = target["published"]["dkp-100"]
        self.assertEqual(row["video_generation_status"], "generated")
        self.assertEqual(row["video_file_name"], "product-100.mp4")
        self.assertEqual(row["filo_upload_status"], "retry")

    def test_editorial_queue_merges_only_this_destination_receipt(self):
        base = state_base()
        source = {
            **base,
            "editorial_delivery_queue": {
                "editorial:delivery-guide": {
                    **base["editorial_delivery_queue"]["editorial:delivery-guide"],
                    "platforms": {
                        **base["editorial_delivery_queue"]["editorial:delivery-guide"]["platforms"],
                        "filo": {"status": "sent", "video_code": "f-1"},
                    },
                }
            },
        }
        target = state_base()
        target["editorial_delivery_queue"]["editorial:delivery-guide"]["platforms"]["youtube"] = {
            "status": "sent", "message_id": "yt-1"
        }
        merge_destination_snapshot(target, base, source, "filo")
        platforms = target["editorial_delivery_queue"]["editorial:delivery-guide"]["platforms"]
        self.assertEqual(platforms["filo"]["status"], "sent")
        self.assertEqual(platforms["youtube"]["message_id"], "yt-1")
        self.assertEqual(platforms["aparat"]["status"], "pending")

    def test_editorial_history_unions_each_destination_without_losing_previous_receipts(self):
        base = state_base()
        source = {
            **base,
            "editorial_delivery_history": [{
                "content_id": "editorial:delivery-guide",
                "editorial_id": "delivery-guide",
                "topic": "delivery",
                "content_fingerprint": "abc123",
                "destinations": {"filo": {"status": "sent", "video_code": "f-1"}},
            }],
        }
        target = {
            **state_base(),
            "editorial_delivery_history": [{
                "content_id": "editorial:delivery-guide",
                "editorial_id": "delivery-guide",
                "topic": "delivery",
                "destinations": {"youtube": {"status": "sent", "message_id": "yt-1"}},
            }],
        }
        merge_destination_snapshot(target, base, source, "filo")
        self.assertEqual(len(target["editorial_delivery_history"]), 1)
        row = target["editorial_delivery_history"][0]
        self.assertEqual(row["destinations"]["youtube"]["message_id"], "yt-1")
        self.assertEqual(row["destinations"]["filo"]["video_code"], "f-1")
        self.assertEqual(row["content_fingerprint"], "abc123")

    def test_root_and_product_state_are_scoped_to_matching_destination_prefix(self):
        base = state_base()
        source = {
            **base,
            "youtube_last_upload_success_at": "2026-11-17T18:00:00+00:00",
            "filo_last_upload_success_at": "2026-11-17T18:05:00+00:00",
            "published": {
                "dkp-100": {
                    **base["published"]["dkp-100"],
                    "youtube_upload_status": "uploaded",
                    "youtube_video_id": "yt-100",
                }
            },
        }
        target = state_base()
        merge_destination_snapshot(target, base, source, "youtube")
        self.assertEqual(target["youtube_last_upload_success_at"], "2026-11-17T18:00:00+00:00")
        self.assertNotIn("filo_last_upload_success_at", target)
        self.assertEqual(target["published"]["dkp-100"]["youtube_video_id"], "yt-100")
        self.assertEqual(target["published"]["dkp-100"]["filo_upload_status"], "pending")

    def test_invalid_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            merge_destination_snapshot(state_base(), state_base(), state_base(), "telegram")


if __name__ == "__main__":
    unittest.main()
