"""Anyaa's voice for the moments the LLM isn't speaking: errors, missing setup, things out of our hands.

The user never sees a stack trace or "Internal Server Error". Lines are picked at random from small
pools so it never feels canned, and they sound like the same warm, practical friend as the agent.
"""

import random

LINES: dict[str, list[str]] = {
    "error": [
        "Oops, something slipped on my side. Could you say that again?",
        "Sorry, I lost my train of thought there. One more time?",
    ],
    "slow": [
        "Sorry, that took longer than it should have. I'm here now.",
    ],
    "instamart_not_connected": [
        "I'll need you to connect Instamart once, the button is right there on your screen.",
    ],
    "instamart_down": [
        "Instamart isn't answering right now. I'll keep the list ready and we can try again in a bit.",
    ],
    "limit": [
        "I need a short break, I've been talking a lot today. Give me a little while and I'm all yours.",
    ],
    "not_ready_yet": [
        "You're all set up. Planning the actual meals is the next thing I'm learning, so hang tight.",
    ],
}


def say(kind: str) -> str:
    return random.choice(LINES[kind])
