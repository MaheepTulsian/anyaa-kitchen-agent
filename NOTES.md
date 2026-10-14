# Build notes

Decisions made while building, where the spec was silent or we deviated.

## Foundation

- **uv + `pyproject.toml` instead of `requirements.txt`.** Lockfile gives reproducible Docker builds.
- **Dependencies are added in the milestone that first uses them**, not all up front.
- **POC, kept lean:** config is plain `os.getenv` (compose loads `.env`), no lint/type tooling,
  no unit tests for plumbing. Only extra dependency: `tzdata` (timezone data in slim containers).
- **Docker is the only way the server runs.** Compose mounts `app/` with `--reload` for development.
- **`models/` is a package** split by concern (enums, household, plan, conversation, state) and
  re-exported from `app.models`. All models reject unknown fields so LLM output drift fails loudly.
- **Allergens are forced to `hard` in the model itself**, so no code path can store a soft allergen.
- **Schema additions:** `cook_profile.household_cooks` (the "no cook, family cooks" case),
  `plan_slot.side_dish_ids_json`, and a `sim_clock` table for the per-household simulated clock.
- **`Variation.ingredient`** (new, optional): the ingredient being omitted or swapped, as a
  canonical id. The validator needs a structured value rather than parsing free text in `detail`.
- **Constraint supersede family = (member, kind, value)**, value case-insensitive. A different
  scope for the same value (peanut `ingredient` → `trace`) supersedes; a different value adds a rule.
- **Members are soft-removed** (`active = 0`) so constraints and history stay traceable.
- **Member names are unique per household, case-insensitive** ("papa" updates "Papa").

## Speech

- **Server speech uses Azure's REST API (`httpx`), not `azure-cognitiveservices-speech`.** Same
  features for our needs (TTS with SSML, short-audio STT) with no native libraries in the image.
- **Cook replies are recorded in the browser as 16 kHz mono WAV**, because Azure short-audio STT
  accepts WAV/OGG but not the WebM that `MediaRecorder` produces. Clips are limited to ~60 s.
- **Browser speech uses the Speech JS SDK pinned to 1.52.0** from jsDelivr, authenticated with a
  token from `/api/speech/token` (the browser reuses it for 9 of its 10 minutes).
- **Household TTS speaks sentence by sentence** as text streams in (split on `. ? !` and `।`).
- **English only for now** (household and cook): `SPEECH_LANGUAGE=en-IN`, cook voice
  `en-IN-NeerjaNeural`. Hindi was verified working (`hi-IN-SwaraNeural` TTS and hi-IN STT) and
  comes back by changing `.env` only.

## Instamart

- **Swiggy's Instamart MCP lives at `https://mcp.swiggy.com/im`** (not `/instamart` as the spec
  says). OAuth 2.1 + PKCE with dynamic client registration; it returns a shared public client id
  and accepts `http://localhost:<port>` callbacks.
- **Our own OAuth flow** (`swiggy_oauth.py`) instead of the MCP SDK's auth helper, because the
  login has to round-trip through the web app's callback route. Token is kept in
  `data/swiggy_token.json` (gitignored) and refreshed automatically.
- **Order safety:** the Swiggy MCP can place real cash-on-delivery orders that cannot be cancelled.
  Any tool whose name matches order/checkout/place/pay/confirm is refused in code.
- **Mock is the default** (64 SKUs, ₹ prices, one out-of-stock item). Search/cart switch to the real
  MCP only when `INSTAMART_MODE=mcp` and a Swiggy token exists.
- **MCP SDK is v2.3** (`streamable_http_client` + `httpx2`), newer than the spec assumed.
