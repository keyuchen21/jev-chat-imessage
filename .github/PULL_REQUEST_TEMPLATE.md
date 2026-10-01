<!-- One PR, one change. "How tested" must not be empty. -->

## What changed

## Why

<!-- Link the issue, e.g. Closes #12 -->

## How tested

- [ ] Offline tests: `uv run --locked python -B -m unittest discover -s tests`
- [ ] Changed AX parsing → ran `uv run python probe/imessage_probe.py` and pasted the (masked) output
- [ ] Still read-only: no chat.db, no AppleScript, no key events; fill only sets AXValue; never sends
- [ ] No API keys in code (keys live in `~/.config/jev-imessage/env`)
- [ ] User-visible behaviour changed → README.md updated
