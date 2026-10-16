# Meal planning and groceries

## MEAL_PLAN node: agree the week

1. **Today and tomorrow first.** The plan starts from the next meal that can still be cooked: a meal
   counts if its cook visit (or a usual meal time) is at least 30 minutes away, so at 1:34 pm today
   starts with dinner. These are discussed until the household is happy.
2. **Then the whole week.** `plan_the_week` keeps the agreed days exactly and plans the rest of the
   7 days around them (no repeated dishes). The grocery list is written later, when GROCERIES opens.
3. **Agree.** On a yes the week is locked and GROCERIES opens by itself.

When something is rejected, Anyaa picks the replacement herself. Rule-like feedback ("we don't eat
rice at dinner") is saved as a strict note first, so it holds for every day, not just the one noticed.

## The planner (`app/planner.py`, `prompts/planner.md`)

Fast steps instead of one huge answer:
1. **Sketch**: one small call: what's cooked for whom on every day (keeps variety across days).
2. **Details**: one call per day, in parallel: every ingredient (including oil, tempering, garnish),
   per-person `cook_note` at the exact step, a one-line `why`.
3. **Safety check**: a separate call whose only job is to compare every dish and ingredient against
   every person's strict notes and diet. Unsafe days are rewritten (at most twice). A plan with open
   issues can't be agreed.

How it plans:
- **Safety**: strict notes are absolute, including oil, tempering and garnish.
- **Nutrition**: protein in every main meal, vegetables every day (leafy greens a few times a week),
  whole grains and millets alongside white rice, fried or sweet food as a treat, a breakfast that counts.
  Health notes become food changes (diabetes → low-GI, smaller rice; BP → salt after their portion is out;
  gym → extra protein portion).
- **The cook**: one base meal with per-person tweaks; a separate dish only when a diet requires it, from a
  shared base; about three components per meal; reuse within a visit; fits the visit's minutes; quick
  meals on the cook's day off; favours dishes the cook makes well. Cook notes say what, never why.
- **The family**: their routine on weekdays, something special at weekends, their favourites placed on
  good days, dislikes never planned.

Changes are cheap: a new sketch with the request, and only the days whose dishes changed are rewritten.

## GROCERIES node and the cart (`app/cart.py`)

One yes: Anyaa summarises the week's list, then fills the Instamart cart:
1. Search Instamart for each line (four at a time).
2. One LLM call picks the product and pack count per line (everyday brands, no overbuying, never
   something that breaks a strict note, in stock only).
3. Fill the cart (this replaces the Instamart cart; it never checks out).
4. Fresh vegetables and herbs, plus anything Instamart didn't have, go on a `wa.me` link for the sabziwala.

Things the cook reports as finished or low are added to the existing Instamart cart (never replacing it),
and the family is asked to place the order (see [cook.md](cook.md)).
