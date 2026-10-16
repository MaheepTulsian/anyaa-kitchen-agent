-- One household per database file. Lists are JSON text; times are ISO 8601 in Asia/Kolkata.

CREATE TABLE IF NOT EXISTS household (
  id INTEGER PRIMARY KEY CHECK (id = 1),       -- always a single row
  phase TEXT NOT NULL DEFAULT 'FAMILY',        -- the household agent's current node
  meals_json TEXT NOT NULL DEFAULT '["lunch","dinner"]',
  meals_set INTEGER NOT NULL DEFAULT 0,
  profile_confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS member (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,    -- "Papa", "Sister", "Me"
  relation TEXT,
  age_group TEXT NOT NULL,
  diet TEXT NOT NULL,
  spice_level INTEGER NOT NULL DEFAULT 2,
  diet_confirmed INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS preference (        -- free-form notes the agent writes
  id INTEGER PRIMARY KEY,
  member TEXT,                                 -- NULL = whole household
  category TEXT NOT NULL,
  detail TEXT NOT NULL,
  strict INTEGER NOT NULL DEFAULT 0,
  quote TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cook (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  profile_json TEXT NOT NULL                   -- CookProfile as JSON
);

CREATE TABLE IF NOT EXISTS pantry (
  item TEXT PRIMARY KEY,
  qty REAL NOT NULL,
  unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan (              -- the current meal plan (draft or approved)
  id INTEGER PRIMARY KEY CHECK (id = 1),
  plan_json TEXT NOT NULL                      -- StoredPlan as JSON
);

CREATE TABLE IF NOT EXISTS message (           -- what the UI shows
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_session (     -- Claude Agent SDK session per agent node
  agent TEXT NOT NULL,
  node TEXT NOT NULL,
  session_id TEXT NOT NULL,
  PRIMARY KEY (agent, node)
);

CREATE TABLE IF NOT EXISTS clock (             -- simulated time for demos and evals
  id INTEGER PRIMARY KEY CHECK (id = 1),
  now TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_contact (  -- phone ↔ Telegram chat, linked when they open the bot
  phone TEXT PRIMARY KEY,                      -- last 10 digits
  chat_id INTEGER NOT NULL,
  name TEXT,
  linked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalation (        -- the cook agent asks the household to pick A or B
  id INTEGER PRIMARY KEY,
  question TEXT NOT NULL,
  option_a TEXT NOT NULL,
  option_b TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent (               -- cook messages already sent (briefs, wrap-ups), so none twice
  key TEXT PRIMARY KEY,
  at TEXT NOT NULL
);
