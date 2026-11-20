CREATE TABLE IF NOT EXISTS oc_affilio_report_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  window_from TEXT NOT NULL,
  window_to TEXT NOT NULL,
  links_total INTEGER,
  links_total_is_capped INTEGER NOT NULL DEFAULT 0,
  links_pages_fetched INTEGER NOT NULL DEFAULT 0,
  links_rows_stored INTEGER NOT NULL DEFAULT 0,
  wallet_finalized_income_amount REAL,
  wallet_balance_amount REAL,
  wallet_days_until_next_invoice INTEGER,
  dashboard_clicks_total REAL,
  dashboard_conversions_total REAL,
  dashboard_revenue_total REAL,
  ingest_status TEXT NOT NULL DEFAULT 'loading',
  github_run_id TEXT,
  github_run_attempt INTEGER
);

CREATE TABLE IF NOT EXISTS oc_affilio_link_analytics (
  snapshot_id TEXT NOT NULL,
  link_uid TEXT NOT NULL,
  link_title TEXT,
  advertiser_name TEXT,
  media_uid TEXT,
  media_name TEXT,
  link_type TEXT,
  link_kind TEXT,
  click_count INTEGER,
  conversion_rate REAL,
  income_items_count INTEGER,
  total_income REAL,
  revenue_share REAL,
  first_click_date TEXT,
  created_at TEXT,
  utm_campaign TEXT,
  utm_content TEXT,
  PRIMARY KEY (snapshot_id, link_uid),
  FOREIGN KEY (snapshot_id) REFERENCES oc_affilio_report_snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_oc_affilio_link_media
  ON oc_affilio_link_analytics(media_uid, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_oc_affilio_link_title
  ON oc_affilio_link_analytics(link_title);

CREATE TABLE IF NOT EXISTS oc_affilio_performance_breakdowns (
  snapshot_id TEXT NOT NULL,
  metric TEXT NOT NULL CHECK (metric IN ('clicks', 'conversions', 'revenue')),
  item_type TEXT NOT NULL,
  value REAL,
  percentage REAL,
  PRIMARY KEY (snapshot_id, metric, item_type),
  FOREIGN KEY (snapshot_id) REFERENCES oc_affilio_report_snapshots(snapshot_id)
);
