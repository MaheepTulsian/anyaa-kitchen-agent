# Anyaa Kitchen Agent

A voice agent for the household kitchen. It plans meals with the family, turns the plan into
groceries (Instamart cart or a WhatsApp list), and then works with the cook day to day.

> Work in progress. This README grows with each milestone.

## Run

Requires Docker.

```bash
cp .env.example .env        # fill in keys (optional until the agent milestone)
docker compose up --build
```

- Health: <http://localhost:8000/health>
- State: <http://localhost:8000/api/state>

## Develop

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest               # tests
uv run ruff check .         # lint
uv run ruff format .        # format
uv run mypy app tests       # strict type-check
```

## Layout

```
app/
  config.py      typed settings (pydantic-settings)
  models/        every boundary type: enums, household, plan, conversation, state
  store/         SQLite schema + one repository module per aggregate
  services/      read models and use-cases built on the store
  api/           FastAPI routes and dependencies
  events.py      append-only JSONL event log (secrets redacted)
  clock.py       per-household simulated clock
tests/
```

## Real vs simulated

| Integration | Status |
|---|---|
| LLM (Anthropic, `claude-haiku-5-5`) | Not wired yet |
| Speech (Azure) | Not wired yet |
| Instamart | Mock by default |
| WhatsApp | `wa.me` links only (one-way) |
| Clock | Simulated, per household |
