# The cook agent (Telegram)

The household hears from Anyaa rarely; the cook hears from her every visit. That's deliberate: the cook
sees what actually happens in the kitchen, so the cook is where ongoing context comes from.

## Channel

A real Telegram bot (`app/telegram.py`). The cook opens the bot once, taps Start and shares their number
with one button; from then on Anyaa can message that number. Replies come in by long polling, so no
public URL is needed. Voice replies are transcribed with Azure (OGG/Opus). WhatsApp would need paid,
pre-approved templates to message first, so Telegram is the POC channel.

## The cook's day (`app/cook.py`)

| When | What | How |
|---|---|---|
| Before each visit (2 h before; early mornings: 9 pm the night before) | **Household check**: "Coming up: Raju's evening visit. Dinner is … Want to change anything before I brief them?" | A message in the family's chat; a change goes through the planner before the brief |
| Start of each visit | **Visit brief**: what to make and for whom, per-person tweaks, prep due before leaving ("soak 250 g rajma"), an invite to reply. No recipes: the cook is a professional | One structured LLM call (`prompts/cook_brief.md`), sent as text + a voice note |
| Whenever the cook replies | **COOK_CHAT** node handles it | Agent with cook-only tools |
| End of each visit | **Wrap-up**: anything finished, left over, did everyone eat | Fixed friendly text |

The simulated clock follows real time plus an offset; `POST /api/clock/advance` jumps to the next
visit event and sends it. Each message is sent at most once.

## How the two sides stay in sync (`app/bridge.py`)

| One side does | The other side hears |
|---|---|
| Family changes a meal the cook was **already briefed** for | Cook gets "Small change from the family: tonight's dinner: …" on Telegram right away |
| Family changes a later meal | Nothing yet; it's in the next brief |
| Cook says something ran out | **Code picks the meal** (the next not-yet-cooked one that uses it); only that meal is re-planned, makeable right now (no soaking). Family gets one message: what changed + cart status |
| Cook says something is low | Added to the Instamart cart (never replacing it); family asked to order |
| Family answers an A/B question | Cook hears the answer and the new menu |

Briefs, checks and heads-ups are sent outside agent turns, so both agents get the latest messages of
their chat (and a few from the other side) in their context, and can answer "ok" or "why?" correctly.

## COOK_CHAT tools (`app/tools/cook.py`)

| The cook says | Tool | What happens |
|---|---|---|
| "paneer khatam" | `report_missing` | The planner swaps only what's needed, **the safety check runs again**, the plan updates, the household is told about the changed meal only, and the item is **added to the Instamart cart** with a "please order" message. No safe swap → `ask_household` |
| "1 ghanta late" / "can't come" | `report_late` / `report_absent` | Quicker meal (checked) / the household picks A or B |
| "ye kaise banate hain" | `dish_help` | Steps from the dish's ingredients and cook notes |
| "atta running low" | `report_stock` | Picks the product, **adds it to the Instamart cart without replacing what's there** (if the cart can't be read safely, it isn't touched), and messages the family to place the order |
| "dal bach gayi" | `report_leftovers` | The planner can use the leftovers |
| "Sushil ji ne sabzi nahi khayi" | `report_feedback` | A soft note that shapes future plans |
| "aaj chole bana doon?" | `ask_household` | The family decides A or B in their chat; the answer goes back to the cook |

## Guardrails

- The cook agent's context never contains the household's notes, so it **can't** leak a diagnosis.
  Cook notes from the planner say only what to do ("less salt for Papa ji"), never why.
- It can't change allergies or diet rules: every menu change goes through the planner and its safety
  check; anything it can't settle safely goes to the household as A/B.
- Respectful (didi / bhaiya / ji), short, never scolds, never discusses pay or leave ("that's between
  you and the family").
