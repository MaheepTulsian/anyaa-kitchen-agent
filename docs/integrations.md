# Integrations

| | Status | Where |
|---|---|---|
| LLM | **Real**: Claude Agent SDK on the local Claude login (`LLM_MODEL=sonnet`) | `app/agent.py` |
| Speech | **Real**: Azure Speech, `en-IN` | `app/speech.py`, `web/js/speech.js` |
| Instamart | **Real** Swiggy MCP when logged in, otherwise a **mock** | `app/swiggy.py`, `app/instamart.py` |
| WhatsApp | `wa.me` links only (one-way) | planned |
| Clock | **Simulated**, stored in the DB | `app/clock.py` |

## Speech

- **Household (browser):** Azure Speech JS SDK (pinned 1.52.0). Push-to-talk STT with a phrase
  list of family and dish words; replies spoken sentence by sentence through one shared
  synthesizer (so sentences never overlap). The browser gets a 10-minute token from
  `/api/speech/token`; the key never leaves the server.
- **Cook (server):** Azure REST via `httpx` (no native SDK in Docker). Brief voice notes are SSML
  synthesised straight to OGG/Opus, which Telegram plays as a voice note. The cook's voice replies
  (OGG/Opus from Telegram) go to Azure short-audio STT as they are.
- **English only for now.** Hindi was tested (`hi-IN-SwaraNeural`, hi-IN STT) and comes back by
  changing `.env`.

## Instamart (Swiggy MCP)

- Server: `https://mcp.swiggy.com/im`. OAuth 2.1 + PKCE with dynamic client registration; the
  user logs in with phone + OTP once (planned as part of onboarding). Token in
  `data/swiggy_token.json`, refreshed automatically.
- **Allowlist, not blocklist.** Swiggy exposes 16 tools, including `checkout` (real,
  non-cancellable cash-on-delivery orders), payments and address edits. Only five can be called:
  `get_addresses`, `search_products`, `your_go_to_items`, `get_cart`, `update_cart`.
- `update_cart` **replaces the whole cart**, so the agent must confirm first. Quantities are capped
  at Swiggy's per-order limit. Results are read from the tool's structured JSON.
- **Mock** (`data/mock_instamart.json`, 64 SKUs with ₹ prices, one out of stock) is used unless
  `INSTAMART_MODE=mcp` and a Swiggy token exists.

## Agent SDK in Docker

The SDK wheel bundles the Claude CLI (113 MB). `uv` can't resume a broken download, so
`scripts/fetch-agent-sdk.sh` fetches it with `curl` (resumable, sha256-checked) into `vendor/`
and the image installs it from there. Inside Docker the agent logs in with
`CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`).

**POC assumption: the address is always serviceable.** When Swiggy answers "not serviceable at the moment"
(late night, store closed), the cart step re-runs on the mock catalog so the flow carries on. The server
log says so (`instamart not serviceable right now, using the mock cart`). Any other Swiggy error is still
shown as an error.
