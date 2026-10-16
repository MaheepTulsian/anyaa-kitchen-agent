# Agents, nodes and guardrails

Anyaa has **two agents**, each a set of **nodes**. Plain code decides which node is active.

```
HOUSEHOLD  FAMILY → FOOD_NEEDS → TASTES → KITCHEN → CONFIRM → MEAL_PLAN → GROCERIES → RUNNING
COOK       VISIT_BRIEF (on the clock) · COOK_CHAT (Telegram replies) · WRAP_UP (on the clock)
                          both write to one shared database
```

- **Household**: few, short encounters. The agent proposes, the user says yes.
- **Cook**: talks every visit. The cook is where ongoing context comes from (stock, leftovers, who ate
  what), so the household doesn't have to be asked.

## What a node is (`app/flow.py`)

| Part | What it is |
|---|---|
| `prompts` | system prompt files: the agent's persona, shared rules, the node's own prompt |
| `tools` | the **only** tools this node can call. Cook tools don't exist in the family node, so it can't ask about the cook. |
| `context` | live data on every message: the time, the household as saved (with #ids), parked notes, recent conversation when a node starts. The cook's context never includes health notes. |
| `scope` | one line repeated at the very end of every message: what this node may talk about |
| `opener` | the node speaks first as soon as it becomes active |

A node ends only through its `*_done` tool, whose requirements are checked in code (e.g. FAMILY
refuses while any diet was guessed rather than confirmed). The finishing node stays quiet and the next
one opens in the same response, so the user sees one reply.

## Guardrails, and the failures they came from

From real test conversations:

| What went wrong | Guardrail now |
|---|---|
| The family node asked about allergies and the cook; facts were said where no tool could save them, a curd intolerance was lost, curd rice was planned | Per-node tools; `park_for_later` in every onboarding node keeps out-of-topic facts; later nodes sort them; `confirm_profile` refuses while anything is parked; the scope line at the end of every message |
| The model echoed its prompt (`<context>`, `[start]`, `<thinking>`) | Replies are cleaned in code before anyone sees them; the persona's first rule forbids it |
| Stage directions like "(waiting on their answer)" replaced the real question | The reply is the last *real* spoken text of the turn, not just the last text |
| Asked a name, asked questions that change nothing, recapped in every node | Explicit "never" lists in the persona and onboarding rules, with the real examples |
| Copied example sentences ("Monday to Saturday, keep Sunday simple") | Examples rewritten as shapes, plus "never copy example sentences" |
| Called tomorrow's breakfast "tonight" | Plan summaries label meals "today / tomorrow / weekday" relative to the clock |
| "No rice at dinner" fixed once, broken again next day | Rule-like feedback is saved as a strict note before the plan is changed |
| Asked the user to choose after they said "you decide" | The persona is decisive by design; the meal-plan node picks replacements itself |
| A friend saved twice ("Friend" and "Sushil") | `upsert_member(previous_name=…)` renames instead of duplicating |

## One turn (`app/agent.py`)

1. Find the node, build `<context>` (ending with the scope line), resume the node's SDK session.
2. The **Claude Agent SDK** runs the tool loop with only that node's tools; a hook logs every call.
3. Clean the reply, save it and the session id; if the node changed, the next node opens.

Everything runs on the Claude Agent SDK (`tools=[]`, `setting_sources=[]`: only our tools, no local
settings). One-shot structured calls (planner, safety check, cook brief, cart picks) use its structured
output (`app/llm.py`).
