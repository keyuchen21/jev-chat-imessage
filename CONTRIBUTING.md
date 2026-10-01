# Contributing

1. Open or pick an issue and comment that you are working on it.
2. Keep the hard rules in [AGENTS.md](AGENTS.md): read-only, never send, no keys in files.
3. Test the layer you change:
   - AX parsing: `uv run python probe/imessage_probe.py`, then the offline tests.
   - Everything: `uv run --locked python -B -m unittest discover -s tests`
4. One PR, one change. Update README.md when user-visible behaviour changes.
