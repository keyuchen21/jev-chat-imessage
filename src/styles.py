"""Built-in tone presets — one label + one instruction per tone.

These are what the generation prompt asks the model to write in; the user picks up to
MAX_SLOTS of them from the HUD. Keeping them here (rather than inline in the prompt) means
one place to add a tone, and lets the parser strip any label the model echoes back.

Each `prompt` is written as a direct instruction to the model: say what the tone IS, and
what it must not become. Vague one-word tones ("funny") produce generic replies — the
useful part is the constraint.
"""

from __future__ import annotations

import re

import userconfig

# How many candidates one generation call can produce. The HUD shows exactly this many
# dropdowns; the panel's candidate area is built for this many rows.
MAX_SLOTS = 3

# Candidates per tone. Each tone gets its own request (they run concurrently), and the
# replies in one response are the same voice at different levels of nerve. The setting is
# read once at startup so the HUD, prompt and parser all use the same row count.
DEFAULT_PER_TONE = 2
MIN_PER_TONE = 1
MAX_PER_TONE = 5


def candidate_count(raw: str | None) -> int:
    """Return a safe candidate count, falling back for malformed startup config."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_PER_TONE
    return value if MIN_PER_TONE <= value <= MAX_PER_TONE else DEFAULT_PER_TONE


def validate_candidate_count(raw: str) -> int:
    """Validate a value written by the settings UI, with a user-facing error."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError("Candidates per tone must be a whole number from 1 to 5") from None
    if not MIN_PER_TONE <= value <= MAX_PER_TONE:
        raise ValueError("Candidates per tone must be a whole number from 1 to 5")
    return value


PER_TONE = candidate_count(userconfig.get("JEV_CANDIDATES_PER_TONE"))

# Reply language: menu title -> the language name the prompt uses. Default English: small
# models (glm-4-flash on the built-in channel) drift into Chinese when told only "same
# language as the message", so the default names one language outright.
SAME_LANGUAGE = "Same as message"
REPLY_LANGUAGES: dict[str, str] = {
    "English": "English",
    SAME_LANGUAGE: "",
    "简体中文": "Simplified Chinese",
    "繁體中文": "Traditional Chinese",
    "Español": "Spanish",
    "Français": "French",
    "Deutsch": "German",
    "日本語": "Japanese",
    "한국어": "Korean",
}
DEFAULT_REPLY_LANGUAGE = "English"


def reply_language(raw: str | None) -> str:
    """Return a known menu title, falling back to English for unset or malformed config."""
    value = str(raw or "").strip()
    return value if value in REPLY_LANGUAGES else DEFAULT_REPLY_LANGUAGE


def validate_reply_language(raw: str) -> str:
    value = str(raw).strip()
    if value not in REPLY_LANGUAGES:
        raise ValueError("Reply language must be one of: " + ", ".join(REPLY_LANGUAGES))
    return value


def language_rule(title: str) -> str:
    """The prompt's language rule for a menu title."""
    name = REPLY_LANGUAGES.get(title, "English")
    if not name:
        return "Write the replies in the same language as the message"
    return (f"Write every reply in {name} only, even when the message or the conversation "
            f"is in another language")


REPLY_LANGUAGE = reply_language(userconfig.get("JEV_REPLY_LANGUAGE"))

# label -> instruction. Order here is the order shown in the dropdowns.
#
# Each entry is written as a *persona plus its verbal tics*, not as a description of a mood.
# "relaxed with a bit of humour" gives the model nothing to hold on to and every tone drifts toward
# the same bland helpfulness; naming who is talking and which words they reach for is what
# actually separates the voices. The trailing constraint matters as much as the rest: a tone
# with no ceiling slides back into generic politeness by the second line.
BUILTIN: dict[str, str] = {
    "Warm & tactful": (
        "The colleague everyone likes: first acknowledge how they feel (\"I get it\", \"fair point\"), "
        "then give the facts and the next step; a no always comes with an alternative and a concrete time. "
        "No lecturing, no rambling, no stack of softeners like \"just\" or \"maybe\"."
    ),
    "Short & clear": (
        "A senior engineer who has seen it all: no preamble, no apology, no explanation — only the "
        "answer plus a time (\"By 3pm.\", \"Confirmed, all good.\"). Short sentences about the task, "
        "not about feelings. Never more than one sentence."
    ),
    "Friendly casual": (
        "A close friend texting back: relaxed, lowercase is fine, contractions everywhere "
        "(\"yeah\", \"sounds good\", \"lol\" at most once), one light joke allowed. "
        "Never stiff phrases like \"Dear\" or \"Kind regards\"; never mean."
    ),
    "Professional": (
        "A calm account manager: polite, precise, complete sentences, states what will happen and when. "
        "No slang, no emoji, no exclamation marks, no over-thanking; stays friendly, not cold."
    ),
    "Polite decline": (
        "Calm but final: say clearly you cannot do it, and leave no opening like \"I'll try\" or "
        "\"maybe later\" that invites more pressure. Offer one concrete alternative or time if there is one. "
        "At most one sentence of apology and one sentence of reason."
    ),
    "Playful": (
        "Light teasing with a grin: exaggerate a detail from their message, play along with the bit, "
        "end with something easy to reply to. Silly is fine, sarcasm is not; never at their expense."
    ),
    "Flirty": (
        "Confident and a little cheeky: a playful push (teasing, contrast or a vivid image), then toss the "
        "ball back with an easy opening; compliment a specific detail, never a generic one. "
        "Bold but never sleazy: no mind games, no put-downs; if they do not bite, let it go lightly."
    ),
    "Cool & detached": (
        "When they are cold, vague or reply \"haha\" only: do not chase, do not explain, do not try to save "
        "face — close this round gracefully in one line (\"Go do your thing, ping me later\") and leave the next "
        "move to them. No passive aggression, no sulking, no long goodbye."
    ),
    "Supportive": (
        "A good listener: name what they seem to feel, show you are on their side, then offer one small "
        "concrete thing (a question, help, a plan). One idea per message. No toxic positivity, no "
        "unasked-for advice, no \"at least…\"."
    ),
    "Witty": (
        "Dry, quick humour: one clever twist or understatement on what they said, then still answer the "
        "actual point. Smart, not try-hard: no puns stacked on puns, no memes they would not get, never mean."
    ),
}

# What the panel starts with. hud.py caps the list at MAX_SLOTS, so this can grow without
# touching the panel build.
DEFAULT_SLOTS: list[str] = ["Warm & tactful", "Friendly casual", "Short & clear"]
NONE_LABEL = "Off"           # a dropdown's way of saying "this slot is switched off"

CUSTOM_VAR = "JEV_TONES"     # env var holding user-defined tones

# Custom tones under this many characters are refused, not loaded. A two-word
# instruction ("praise me") gives the model nothing to hold on to — the candidates come back
# generic, and the panel wears it as our fault. The built-ins run 60–120 chars; 10 is a
# floor that still admits one honest sentence while blocking pure noise. Refusals land
# in REJECTED_TONES so the startup log can point at the fix.
MIN_TONE_DESC_CHARS = 10
REJECTED_TONES: list[str] = []


def _custom_tones() -> dict[str, str]:
    """Tones the user defined in their env file, as `name=description` entries separated by `|`.

        export JEV_TONES="Pirate=talk like a friendly pirate, never rude|Coach=upbeat sports coach, short pep talk"

    A same-named entry overrides the built-in one, so the shipped wording can be tuned
    without touching this file. A tone called NONE_LABEL ("Off") is dropped: that label is the panel's
    sentinel for "this slot is switched off", and letting a tone shadow it would make a
    slot impossible to switch off. Descriptions shorter than MIN_TONE_DESC_CHARS are
    refused and recorded in REJECTED_TONES (see that constant).
    """
    raw = userconfig.get(CUSTOM_VAR)
    out: dict[str, str] = {}
    for part in (raw or "").split("|"):
        name, sep, desc = part.partition("=")
        name, desc = name.strip(), desc.strip()
        if sep and name and name != NONE_LABEL:
            if len(desc) < MIN_TONE_DESC_CHARS:
                REJECTED_TONES.append(
                    f"\"{name}\" has only {len(desc)} characters (at least {MIN_TONE_DESC_CHARS}; "
                    "say what the tone is and what it must not become)")
                continue
            out[name] = desc
    return out


CUSTOM: dict[str, str] = _custom_tones()
PRESETS: dict[str, str] = {**BUILTIN, **CUSTOM}

def _label_alternation() -> str:
    """The labels as one regex alternative, with spaces and 「·」 made optional.

    "Short & clear" is written with spaces in the dropdown but the model may echo it
    without them ("Short&clear:") — matching the space loosely costs nothing and avoids a
    label that leaks through only sometimes. The same applies to the middle dot in
    a label like "A·B": the model drops it about as readily as a space, so "·" also matches
    zero-or-one instead of exactly one.
    """
    escaped = (re.escape(k).replace(r"\ ", r"\s*").replace("·", "·?")
               for k in sorted(PRESETS, key=len, reverse=True))
    return "|".join(escaped)


_LABEL_RE = re.compile(
    rf"^[*_#\s]*(?:{_label_alternation()})[^，。！？；、,.!?;：:]{{0,4}}[*_#\s]*[:：]\s*")


def labels() -> list[str]:
    """All preset labels, in dropdown order."""
    return list(PRESETS)


def strip_label(line: str) -> str:
    """Remove a leading preset label the model echoed back, e.g. "Friendly casual: sounds good".

    The model is told not to label its lines, and usually complies — but the prompt itself
    shows it these labels, so now and then it echoes one. Because the labels are data, they
    are stripped from the same place they are defined: adding a tone here cannot silently
    break the parser the way a hardcoded list would.
    """
    return _LABEL_RE.sub("", line)
