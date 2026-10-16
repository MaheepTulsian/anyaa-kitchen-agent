# Anyaa: write-up

## What it is

A voice agent for the Indian household kitchen with two jobs. **With the household**, it learns the
family in a short conversation, proposes the week's meals (today and tomorrow first, then the rest),
and fills the Instamart cart with one yes, with vegetables going to the sabziwala as a WhatsApp list.
**With the cook**, it first shows the family what's coming ("change anything?"), then sends the cook a
short brief and a voice note on Telegram, handles their replies ("paneer khatam", "1 ghanta late",
"atta running low") and checks in at the end. Whatever one side does, the other hears about.

## Key decisions

1. **The household barely talks; the cook talks every day.** The person running the kitchen is tired of
   deciding. So Anyaa proposes and they say yes; onboarding is about five short parts, the week is one
   or two turns, groceries one yes. Ongoing context (what ran out, what was left, who didn't eat the
   bhindi) comes from the cook, who sees it first.
2. **Two agents, nodes, code in charge.** A household agent and a cook agent on the Claude Agent SDK.
   Each node has its own prompt, only its own tools, and a code-checked exit, so the model can't skip a
   step or wander into another topic's tools. Two agents also keep privacy structural: the cook agent's
   context never contains the family's health notes, so it can't leak "Papa's BP".
3. **Safety is a separate step.** Planning juggles taste, nutrition, variety and the cook's time, so an
   allergy is easy to drop. A second, focused LLM call checks every dish and ingredient (oil, tempering,
   garnish) against every strict note and diet; unsafe plans can't be agreed. Every cook-side change
   (a swap, a quicker dish) goes through the same check, and anything unsafe goes to the family as A/B.
4. **Free-form notes, not a schema.** Families say things that don't fit fields ("itchy with arbi, but
   traces are fine", "no rice at dinner"). Everything is a short note with `strict` and the user's exact
   words, which the planner and the checker read directly.
5. **Prompts written against observed failures.** Each guardrail traces to a real test: facts lost
   when asked in the wrong part (now parked and sorted later, and confirm refuses until they are), the
   model echoing its prompt or stage directions (cleaned in code), copied example lines, "tonight" for
   tomorrow's breakfast, asking the user to choose after "you decide".
6. **Code decides the risky parts, not the model.** Which meal a cook-side swap may touch (the next
   not-yet-cooked meal that uses the missing item; nothing else changes), whether a diet matches the
   user's own words, what the confirmation summary says (facts written by code), whether the cook must
   hear about a family change now (only if already briefed). Each of these was a real failure first.
7. **One meal, small tweaks.** The planner aims for one base meal per sitting with per-person changes at
   the exact step ("take out Papa ji's portion before the salt"), and a separate dish only when a diet
   requires it, from a shared base. Nutrition (protein every meal, greens, whole grains, treats as
   treats) is planned in, but spoken about only through taste.

## Trade-offs

- **Claude Agent SDK on a subscription login** during development: simple and capable, but each turn
  starts a CLI process (about 5 to 10 seconds) and usage limits apply. Planning a week takes about a
  minute even split into parallel steps; it starts in the background the moment the profile is confirmed.
- **Haiku by default** for cost. Sonnet labelled diets more reliably; the code-side guardrails (diet
  confirmation, parking, the safety check) are there so the cheaper model stays safe.
- **Instamart serviceability is assumed**: late at night Swiggy reports the address as not serviceable;
  that cart step then runs on the mock catalog (logged) so the flow can be shown at any hour.
- **Telegram instead of WhatsApp** for the cook: WhatsApp Cloud API needs paid templates to message first.
  The sabziwala still gets a WhatsApp list as a `wa.me` link.
- **Instamart cart only**: the Swiggy MCP can place real cash-on-delivery orders, so only five tools are
  allowlisted; it never checks out.

## How it stays performant today, without an eval suite

Every turn is logged (`logs/events.jsonl`: node, tool calls with arguments and results, reply, timings).
Each conversation I ran was read from these logs. Every failure became a code guard or a prompt rule with
the real example (the table in `docs/agents.md`). Guards in code don't regress when a prompt changes;
the eval suite below is what's missing to catch prompt regressions automatically.

## Left out on purpose

Evals (next, see below), payments and ordering, Hindi and other languages for the cook (tested, switched off for
now), nutrition maths and calorie counts, pantry tracking beyond what the cook reports, multiple
households, accounts and auth, continuous listening.

## What's next

1. **Evals**: scripted messy households run end to end by a simulated user; check strict-note recall,
   zero safety issues in plans, parked notes sorted, turns to confirm, tone, latency (from the turn logs).
2. Hindi and Kannada voice notes for cooks (Hindi already works through Azure, switched off); WhatsApp
   Business API with templates instead of Telegram.
3. Learning from cook feedback over weeks (dishes left uneaten drop out, favourites come back).
4. Faster turns on the Anthropic API directly, with prompt caching for the persona.
