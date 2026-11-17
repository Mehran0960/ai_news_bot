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

    def test_latest_channel_timestamp_wins(self):
        base={"last_channel_published_at":"2026-11-17T10:00:00+00:00"}
        ours={"last_channel_published_at":"2026-11-17T10:05:00+00:00"}
        theirs={"last_channel_published_at":"2026-11-17T10:06:00+00:00"}
        self.assertEqual(three_way_merge(base,ours,theirs)["last_channel_published_at"],theirs["last_channel_published_at"])

if __name__ == "__main__": unittest.main()
