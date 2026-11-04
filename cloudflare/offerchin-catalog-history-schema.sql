-- OfferChin full-catalog state and event history.
-- The existing affiliate-deal-radar tables are left untouched.
CREATE TABLE IF NOT EXISTS offerchin_catalog_products (
  product_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  current_price INTEGER,
  original_price INTEGER,
  discount_percent INTEGER,
  availability TEXT NOT NULL DEFAULT 'unknown'
    CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
  product_url TEXT NOT NULL,
  category_id TEXT,
  first_seen_at TEXT NOT NULL,
  last_changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offerchin_catalog_price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  title TEXT NOT NULL,
  current_price INTEGER,
  original_price INTEGER,
  discount_percent INTEGER,
  availability TEXT NOT NULL
    CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
  category_id TEXT,
  change_type TEXT NOT NULL
    CHECK (change_type IN ('initial', 'price_or_stock_change')),
  changed_fields TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (product_id) REFERENCES offerchin_catalog_products(product_id)
);

CREATE INDEX IF NOT EXISTS idx_offerchin_catalog_history_product_time
  ON offerchin_catalog_price_history(product_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_offerchin_catalog_history_time
  ON offerchin_catalog_price_history(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_offerchin_catalog_products_discount
  ON offerchin_catalog_products(discount_percent DESC, current_price DESC);

CREATE TRIGGER IF NOT EXISTS offerchin_catalog_products_initial_history
AFTER INSERT ON offerchin_catalog_products
BEGIN
  INSERT INTO offerchin_catalog_price_history (
    product_id, observed_at, title, current_price, original_price,
    discount_percent, availability, category_id, change_type, changed_fields
  ) VALUES (
    NEW.product_id, NEW.first_seen_at, NEW.title, NEW.current_price, NEW.original_price,
    NEW.discount_percent, NEW.availability, NEW.category_id, 'initial', 'initial'
  );
END;

CREATE TRIGGER IF NOT EXISTS offerchin_catalog_products_changed_history
AFTER UPDATE OF current_price, original_price, discount_percent, availability
ON offerchin_catalog_products
WHEN OLD.current_price IS NOT NEW.current_price
  OR OLD.original_price IS NOT NEW.original_price
  OR OLD.discount_percent IS NOT NEW.discount_percent
  OR OLD.availability IS NOT NEW.availability
BEGIN
  INSERT INTO offerchin_catalog_price_history (
    product_id, observed_at, title, current_price, original_price,
    discount_percent, availability, category_id, change_type, changed_fields
  ) VALUES (
    NEW.product_id, NEW.last_changed_at, NEW.title, NEW.current_price, NEW.original_price,
    NEW.discount_percent, NEW.availability, NEW.category_id, 'price_or_stock_change',
    trim(
      (CASE WHEN OLD.current_price IS NOT NEW.current_price THEN 'current_price,' ELSE '' END) ||
      (CASE WHEN OLD.original_price IS NOT NEW.original_price THEN 'original_price,' ELSE '' END) ||
      (CASE WHEN OLD.discount_percent IS NOT NEW.discount_percent THEN 'discount_percent,' ELSE '' END) ||
      (CASE WHEN OLD.availability IS NOT NEW.availability THEN 'availability,' ELSE '' END),
      ','
    )
  );
END;
