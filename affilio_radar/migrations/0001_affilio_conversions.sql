-- Affilio conversion events are immutable per (conversion_id, status).
-- This preserves pending -> approved/declined transitions and makes postback retries idempotent.
CREATE TABLE IF NOT EXISTS affilio_conversions (
  conversion_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
  type TEXT NOT NULL CHECK (type IN ('sale', 'lead', 'action')),
  timestamp TEXT NOT NULL,
  aff_sub TEXT,
  payout_toman INTEGER CHECK (payout_toman IS NULL OR payout_toman >= 0),
  amount_toman INTEGER CHECK (amount_toman IS NULL OR amount_toman >= 0),
  items_json TEXT NOT NULL DEFAULT '[]',
  received_at TEXT NOT NULL,
  PRIMARY KEY (conversion_id, status)
);

CREATE INDEX IF NOT EXISTS idx_affilio_conversions_timestamp
  ON affilio_conversions(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_affilio_conversions_aff_sub_timestamp
  ON affilio_conversions(aff_sub, timestamp DESC);
