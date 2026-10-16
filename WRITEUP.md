# Anyaa: write-up

## What it does

- **With the household** (voice in the browser): learns the family in five short parts, plans today and
  tomorrow first and then the rest of the week, and fills the Instamart cart on a yes. Vegetables go to
  the sabziwala as a `wa.me` list.
- **With the cook** (Telegram): before each visit the family sees what's coming and can change it. Then
  the cook gets a short brief (text + voice note). The cook can reply that something ran out, is low,
  they're late, or ask how to make a dish. After the visit there's a wrap-up question.

## Key decisions

- **Anyaa proposes, the family says yes.** Few, short questions for the household. Day-to-day
  information (what ran out, leftovers, feedback) comes from the cook.
- **Two agents built from nodes, on the Claude Agent SDK.** Each node has its own prompt and only its own
  tools. It ends through a `*_done` tool whose conditions are checked in code. The cook agent's context
  doesn't include the family's health notes.
- **Some rules are enforced in code, not left to the prompt:**
  - a diet must match the user's own words;
  - facts said in the wrong part are parked, and the profile can't be confirmed while any are parked;
  - the confirmation summary is built from saved facts;
  - when the cook reports a missing item, code picks the one meal that may change;
  - the cook hears about a family change at once only if they were already briefed for that meal.
- **A separate safety check.** After planning, a second LLM call checks the dishes and ingredients
  against strict notes and diets. A plan with open issues can't be agreed.
- **Free-form notes.** Preferences are short notes with `strict` and the user's exact words, rather
  than fixed fields.

## Trade-offs

- **Agent SDK on a Claude subscription login:** no API credits needed, but each turn starts a CLI
  process, so replies are slow-ish and usage limits apply. Planning a week takes about a minute.
- **Haiku by default** to keep cost low. The code checks above matter more because of it.
- **Telegram instead of WhatsApp** for the cook: WhatsApp Cloud API needs paid templates to message first.
- **Instamart is cart only.** Five Swiggy MCP tools are allowlisted, and none of them places an order.
  If Swiggy says the address isn't serviceable right now, that cart step uses the mock catalog
  instead (logged).

## Left out

- Evals.
- Ordering and payments.
- Hindi and other languages: English only; Hindi voices are a config change.
- Nutrition numbers.
- Pantry tracking beyond what the cook reports.
- Multiple households and accounts.

## How I checked it

Every turn is logged to `logs/events.jsonl` (node, tool calls with results, reply, timings). I read the
logs of each test conversation and turned failures into code checks or prompt rules (listed in
`docs/agents.md`). There's no automated eval suite yet.

## What's next

1. **Evals:** scripted messy households played by a simulated user, checking strict-note recall, safety
   issues in plans, tone and latency.
2. Hindi voice notes for cooks; WhatsApp Business API.
3. Using cook feedback over weeks to shape plans.
4. The Anthropic API directly with prompt caching, for faster turns.
