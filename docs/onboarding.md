# Onboarding (five household nodes)

Goal: know the household well enough to feed it every day, in a quick, warm chat where the user mostly
answers yes or a few words.

| Node | Covers (and only this) | Ends when (checked in code) |
|---|---|---|
| FAMILY | who eats at home, each person's diet, kids' ages; the promise | someone is saved and **every diet came from the user** |
| FOOD_NEEDS | allergies and intolerances (with traces), health needs, never-eat, fasting | **every person** has an allergy answer, even "none" |
| TASTES | everyday food, favourites, dislikes, spice, how they eat ("no rice at dinner") | an everyday-food or favourite note exists |
| KITCHEN | the cook: name, visits, days off, strengths, phone (Telegram hello); meals to plan, proposed | cook saved and meals agreed |
| CONFIRM | Instamart check (quiet), a crisp summary, "anything I missed?" | nothing parked, summary read with no changes since, then yes |

## Principles

- **Propose, don't ask.** Meals to plan are proposed from the cook's visits; tastes are guessed and
  confirmed.
- **One topic per node.** Things said early are parked (`park_for_later`), never lost, never chased.
- **Unmentioned means none**, but every person must have an allergy answer.
- **Follow up only where it changes safety or the plan**, e.g. whether an allergy includes traces.

## What gets stored

- **Members**: name as the family says it, age group, diet (and whether the user confirmed it).
- **Preferences**: free-form notes, one list for everything:

  ```json
  {"member": "Sushil", "category": "intolerance", "detail": "curd and anything made with it: lassi, raita, kadhi",
   "strict": true, "quote": "He cannot eat curd or curd related dishes like lassi, raita or kadhi"}
  ```

  `strict` marks what must never be broken; `quote` keeps the user's exact words.
- **Cook**: visits, days off, dishes they know, weak spots, phone.
- **Meals to plan**, optional pantry, Instamart connection.

The prompts are layered: `household_persona.md` (who Anyaa is), `onboarding_rules.md` (the one-topic
rule, parking, the failures to avoid), and one file per node in `prompts/nodes/`.
