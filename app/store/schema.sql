-- One household per DB file. List-like fields are JSON text; timestamps are ISO 8601 (Asia/Kolkata).

CREATE TABLE IF NOT EXISTS household (
  id INTEGER PRIMARY KEY,
  name TEXT,
  phase TEXT NOT NULL DEFAULT 'ONBOARDING',
  meals_json TEXT NOT NULL DEFAULT '["lunch","dinner"]',
  cuisine_prefs_json TEXT NOT NULL DEFAULT '[]',
  profile_confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS member (
  id INTEGER PRIMARY KEY,
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  relation TEXT,
  age_group TEXT NOT NULL,
  diet TEXT NOT NULL DEFAULT 'veg',
  spice_level INTEGER NOT NULL DEFAULT 2,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE (household_id, name)
);

CREATE TABLE IF NOT EXISTS constraint_ (
  id INTEGER PRIMARY KEY,
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  member_id INTEGER REFERENCES member(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  strength TEXT NOT NULL,
  scope TEXT,
  condition TEXT,
  quote TEXT NOT NULL,
  valid_from TEXT,
  superseded_by INTEGER REFERENCES constraint_(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cook_profile (
  household_id INTEGER PRIMARY KEY REFERENCES household(id) ON DELETE CASCADE,
  name TEXT,
  language TEXT NOT NULL DEFAULT 'hi',
  visits_json TEXT NOT NULL,
  days_off_json TEXT NOT NULL DEFAULT '[]',
  known_dishes_json TEXT NOT NULL DEFAULT '[]',
  household_cooks INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS pantry (
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  item TEXT NOT NULL,
  qty REAL NOT NULL,
  unit TEXT NOT NULL,
  PRIMARY KEY (household_id, item)
);

CREATE TABLE IF NOT EXISTS plan (
  id INTEGER PRIMARY KEY,
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_slot (
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  meal TEXT NOT NULL,
  visit TEXT NOT NULL,
  dish_id TEXT NOT NULL,
  side_dish_ids_json TEXT NOT NULL DEFAULT '[]',
  servings_json TEXT NOT NULL,
  attendees_json TEXT NOT NULL DEFAULT '[]',
  variations_json TEXT NOT NULL DEFAULT '[]',
  prep_tasks_json TEXT NOT NULL DEFAULT '[]',
  locked INTEGER NOT NULL DEFAULT 0,
  stale INTEGER NOT NULL DEFAULT 0,
  why TEXT NOT NULL,
  UNIQUE (plan_id, date, meal)
);

CREATE TABLE IF NOT EXISTS attendance (
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  meal TEXT NOT NULL,
  member_id INTEGER REFERENCES member(id) ON DELETE CASCADE,
  present INTEGER NOT NULL DEFAULT 1,
  guests INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS grocery_item (
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  item TEXT NOT NULL,
  qty REAL NOT NULL,
  unit TEXT NOT NULL,
  pack_qty REAL,
  pack_unit TEXT,
  packs INTEGER,
  channel TEXT NOT NULL,
  needed_by TEXT NOT NULL,
  sku_json TEXT
);

CREATE TABLE IF NOT EXISTS message (
  id INTEGER PRIMARY KEY,
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  agent TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summary (
  household_id INTEGER NOT NULL REFERENCES household(id) ON DELETE CASCADE,
  agent TEXT NOT NULL,
  content TEXT NOT NULL,
  PRIMARY KEY (household_id, agent)
);

CREATE TABLE IF NOT EXISTS sim_clock (
  household_id INTEGER PRIMARY KEY REFERENCES household(id) ON DELETE CASCADE,
  now TEXT NOT NULL
);
