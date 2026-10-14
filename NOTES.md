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
