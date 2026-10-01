---
name: Bug report
about: Report a defect
title: "[Bug] "
labels: bug
---

## What happened

<!-- What you did, what you expected, what happened -->

## Steps to reproduce

1.

## Log

```bash
tail -40 ~/Library/Logs/jev-imessage.log
```

The log has stage timings and **no message text or candidates**, so it is safe to paste.

## Probe (if messages are missing or on the wrong side)

```bash
uv run python probe/imessage_probe.py
```

Text is masked by default. Check the output before you paste it.

## Environment

- macOS version and UI language:
- Started with: start.command / .app
- Judgment: Jev / local decider-2b
- Generation endpoint:
