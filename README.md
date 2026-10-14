# Anyaa Kitchen Agent

A voice agent for the household kitchen. It plans meals with the family, turns the plan into
groceries (Instamart cart or a WhatsApp list), and then works with the cook day to day.

> Work in progress. This README grows with each milestone.

## Run

Requires Docker.

```bash
cp .env.example .env        # fill in keys (optional until the agent milestone)
APP_PORT=8010 docker compose up --build -d   # any free host port
```

- Health: <http://localhost:8010/health>
- State: <http://localhost:8010/api/state>
- Voice lab: <http://localhost:8010/voice-lab.html>

## Layout

```
app/
  config.py      env vars via os.getenv
  models/        every boundary type: enums, household, plan, conversation, state
  store/         SQLite schema + one repository module per aggregate
  services/      use-cases built on the store
  main.py        FastAPI routes
  events.py      append-only JSONL event log
  clock.py       per-household simulated clock
```

## Real vs simulated

| Integration | Status |
|---|---|
| LLM (Anthropic, `claude-haiku-5-5`) | Not wired yet |
| Speech (Azure) | Not wired yet |
| Instamart | Mock by default |
| WhatsApp | `wa.me` links only (one-way) |
| Clock | Simulated, per household |
