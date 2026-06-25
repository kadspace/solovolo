CREATE TABLE IF NOT EXISTS seen_activities (
  id TEXT PRIMARY KEY,
  sport TEXT,
  name TEXT,
  type TEXT,
  date TEXT,
  start_time TEXT,
  end_time TEXT,
  venue TEXT,
  address TEXT,
  neighborhood TEXT,
  spots_available INTEGER,
  male_eligible_spots INTEGER,
  url TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  notified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activity_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id TEXT,
  event_type TEXT NOT NULL,
  details TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watcher_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  trigger TEXT NOT NULL,
  ok INTEGER NOT NULL,
  total_fetched INTEGER NOT NULL DEFAULT 0,
  new_activities INTEGER NOT NULL DEFAULT 0,
  updated_activities INTEGER NOT NULL DEFAULT 0,
  notifiable_activities INTEGER NOT NULL DEFAULT 0,
  notified_activities INTEGER NOT NULL DEFAULT 0,
  pending_notifications INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_seen_notified ON seen_activities (notified);
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log (created_at);
CREATE INDEX IF NOT EXISTS idx_watcher_runs_started_at ON watcher_runs (started_at);
