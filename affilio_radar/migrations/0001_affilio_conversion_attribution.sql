-- Affilio conversion postbacks: immutable status events plus the latest status per conversion.
-- Amounts and payouts are integer Toman. Only latest approved sale rows count as purchases.
CREATE TABLE IF NOT EXISTS affilio_conversion_events (
  conversion_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
  timestamp_ms INTEGER NOT NULL,
  conversion_type TEXT NOT NULL CHECK (conversion_type IN ('sale', 'lead', 'action')),
  aff_sub TEXT,
  product_id TEXT,
  channel TEXT,
  creative_experiment_id TEXT,
  creative_variant TEXT CHECK (creative_variant IS NULL OR creative_variant IN ('A', 'B')),
  caption_experiment_id TEXT,
  caption_variant TEXT CHECK (caption_variant IS NULL OR caption_variant IN ('A', 'B')),
  payout_toman INTEGER,
  amount_toman INTEGER,
  units_sold INTEGER NOT NULL DEFAULT 0,
  items_json TEXT NOT NULL DEFAULT '[]',
  received_at_ms INTEGER NOT NULL,
  PRIMARY KEY (conversion_id, status)
);

CREATE INDEX IF NOT EXISTS idx_affilio_conversion_events_timestamp
  ON affilio_conversion_events (timestamp_ms);

CREATE TABLE IF NOT EXISTS affilio_conversion_current (
  conversion_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
  status_rank INTEGER NOT NULL,
  timestamp_ms INTEGER NOT NULL,
  conversion_type TEXT NOT NULL CHECK (conversion_type IN ('sale', 'lead', 'action')),
  aff_sub TEXT,
  product_id TEXT,
  channel TEXT,
  creative_experiment_id TEXT,
  creative_variant TEXT CHECK (creative_variant IS NULL OR creative_variant IN ('A', 'B')),
  caption_experiment_id TEXT,
  caption_variant TEXT CHECK (caption_variant IS NULL OR caption_variant IN ('A', 'B')),
  payout_toman INTEGER,
  amount_toman INTEGER,
  units_sold INTEGER NOT NULL DEFAULT 0,
  items_json TEXT NOT NULL DEFAULT '[]',
  received_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_affilio_conversion_current_time_status
  ON affilio_conversion_current (timestamp_ms, conversion_type, status);
CREATE INDEX IF NOT EXISTS idx_affilio_conversion_current_product
  ON affilio_conversion_current (product_id, timestamp_ms, status);
