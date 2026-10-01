# AGENTS.md

Copilot panel for macOS Messages.app: read the open chat through the accessibility (AX) tree →
judge intent / risk (TypeSafe Jev or local decider-2b) → generate reply candidates (OpenAI- or
Anthropic-compatible API) → rank → floating panel → one-click fill into the input field.

## Hard rules

1. **Read-only.** No injection, no hooks, no reading `~/Library/Messages/chat.db`, no
   AppleScript. The only write is "fill": set `AXValue` of `messageBodyField` and read it back.
2. **Never send.** Never press Return, never synthesize key events, never touch the send path.
3. **No keys in files, logs or git.** Keys live in `~/.config/jev-imessage/env` (mode 600).
4. **Logs never contain message text, context or candidates.**
5. Jev questions (instructions / criteria) are written in English; chat text in `state`
   stays verbatim. Reply language comes from `JEV_REPLY_LANGUAGE` (default English; see
   `styles.REPLY_LANGUAGES`); the prompt states it twice because small models drift.

## Layout and commands

- `src/apps/imessage_app.py` — the only adapter (AX read, parse, fill). Constants at the top
  (`TranscriptCollectionView`, `messageBodyField`, `MessageEntryView`, `ConversationTitle`).
- `src/apps/registry.py` — dispatch by frontmost bundle id `com.apple.MobileSMS`.
- `src/hud.py` — panel + polling loop; `src/judge.py` local judge; `src/judge_jev.py` Jev;
  `src/generate.py` candidates; `src/styles.py` tones; `src/userconfig.py` env loading.
- `src/perception.py`, `calibration*.py`, `visual_fill.py`, `input_region.py` are the
  screenshot/OCR path inherited from the WeChat app. Messages does not use them today; they
  stay as the OCR fallback (route C) and for `Message` / `WindowInfo`.

```bash
./start.command                                  # run the app
uv run python probe/imessage_probe.py            # AX tree of the open chat (text masked)
uv run python src/apps/imessage_app.py           # adapter read, CLI-verifiable
uv run python -B -m unittest discover -s tests   # offline tests
```

## Known facts

- Message node description: `<sender>, <body>, <time>`; own messages: `Your iMessage, …`.
  The prefix and time format are English-UI facts; direction uses bubble geometry first.
- Compare the bubble's gaps to the pane's left and right edges, not its centre — long
  bubbles cross the middle.
- Scrolled-out messages stay in the tree with frames outside the window; filter by window.
- An empty input reads as `None`, not `""`.
- AX works from a CLI process when the terminal has Accessibility permission.
- Before changing parsing, run `probe/imessage_probe.py` and record the real output in
  `_reports/`.
