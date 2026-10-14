"""Closed vocabularies shared by the store, tools, planner and validator."""

from enum import StrEnum


class Phase(StrEnum):
    ONBOARDING = "ONBOARDING"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    CHECKOUT = "CHECKOUT"
    EXECUTION = "EXECUTION"


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class AgeGroup(StrEnum):
    TODDLER = "toddler"
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    ELDERLY = "elderly"


class Diet(StrEnum):
    VEG = "veg"
    EGGETARIAN = "eggetarian"
    NONVEG = "nonveg"
    JAIN = "jain"
    VEGAN = "vegan"


class Language(StrEnum):
    HINDI = "hi"
    KANNADA = "kn"
    TAMIL = "ta"
    ENGLISH = "en"


class Unit(StrEnum):
    GRAM = "g"
    MILLILITRE = "ml"
    PIECE = "pc"


class Channel(StrEnum):
    INSTAMART = "instamart"
    SABZIWALA = "sabziwala"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class Agent(StrEnum):
    HOUSEHOLD = "household"
    COOK = "cook"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class VariationChange(StrEnum):
    SALT_SEPARATE = "salt_separate"
    SET_ASIDE_BEFORE_TADKA = "set_aside_before_tadka"
    LESS_SPICE = "less_spice"
    SWAP_SIDE = "swap_side"
    NO_ONION_GARLIC = "no_onion_garlic"
    EXTRA_PROTEIN = "extra_protein"
    SOFT_TEXTURE = "soft_texture"
    SEPARATE_DISH = "separate_dish"
    OMIT_INGREDIENT = "omit_ingredient"


class PrepOwner(StrEnum):
    COOK_PREVIOUS_VISIT = "cook_previous_visit"
    COOK_SAME_VISIT = "cook_same_visit"
    HOUSEHOLD = "household"


class Severity(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class EventType(StrEnum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    VALIDATOR = "validator"
    PHASE_CHANGE = "phase_change"
    COOK_REPLY = "cook_reply"
    ERROR = "error"
