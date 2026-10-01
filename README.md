# jev-chat-imessage

A copilot that sits next to **Messages.app on macOS** (iMessage and SMS). When a new message
comes in, a floating panel shows **what the sender really means**, a **risk level**, and
**reply candidates** ranked by a judgment model. One click puts a candidate into the
Messages input field. **You always press Return yourself — the app never sends.**

**Read-only and non-invasive.** It reads the Messages window through the macOS
accessibility (AX) API. No injection, no hooks, no reading of `~/Library/Messages/chat.db`,
no screenshots, no AppleScript `send`.

Derived from [jev-chat-jarvis-mac](https://github.com/jev-chat/jev-chat-jarvis-mac)
(WeChat / QQ). This repo keeps only the Messages.app adapter.

## How it reads Messages

Probed on macOS 27.2 with the English UI (details: `_reports/imessage-probe_report.md`):

- Each message in the transcript is an AX node whose description is
  `<sender>, <body>, <time>`. Your own messages start with `Your iMessage, …`.
- Direction ("me" / "them") comes from the bubble frame: own bubbles touch the right edge of
  the chat pane, incoming bubbles the left edge. The `Your …` prefix confirms it.
- Messages scrolled out of view stay in the tree; only bubbles inside the window are used.
- The chat title is the `ConversationTitle` button; the input is the `messageBodyField` text
  field, which accepts an AX value write and reads it back.

Check it on your machine (a chat must be open in Messages):

```bash
uv run python probe/imessage_probe.py            # tree, frames, parsed messages (text masked)
uv run python probe/imessage_probe.py --fill hi  # also write "hi" to an empty input, read back, clear
uv run python src/apps/imessage_app.py           # the adapter's own read
```

## Requirements

- Apple Silicon Mac. macOS 13+ inherited from the base app; only macOS 27.2 is tested.
- **Accessibility** permission (System Settings › Privacy & Security › Accessibility) for the
  terminal or the `.app`. Screen Recording is **not** needed.
- Python 3.12 via [uv](https://docs.astral.sh/uv/).

## Run from source

```bash
./start.command                                  # Ctrl+C to quit
uv run python -B -m unittest discover -s tests   # offline tests (fake AX tree, no screen, no API)
uv run python src/generate.py --check            # generation credentials
```

## Configuration

One env file: `~/.config/jev-imessage/env` (mode 600). The settings window (gear icon on the
panel) edits the same file. Restart after changing model settings.

```bash
mkdir -p ~/.config/jev-imessage
cat > ~/.config/jev-imessage/env <<'ENV'
# Judgment (intent, risk, ranking): TypeSafe Jev via OpenRouter
export TYPESAFE_API_KEY=""                       # your OpenRouter key
export TYPESAFE_BASE_URL="https://openrouter.ai/api/alpha/decisions"
export TYPESAFE_MODEL="typesafe/jev-1.13"

# Reply generation: any OpenAI-compatible endpoint (or ANTHROPIC_* for Anthropic format)
export OPENAI_API_KEY=""
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL=""
ENV
chmod 600 ~/.config/jev-imessage/env
```

- Without a judgment key, first launch asks you to choose: online judgment, or download the
  local model (about 3.8 GB). It never downloads without asking.
- Do not use a "thinking" model for generation: the thinking uses up `max_tokens` and no
  candidates come back.
- **Reply language**: English by default. Change it in Settings › Replies · OpenAI
  ("Reply language": English, Same as message, 简体中文, 繁體中文, Español, Français, Deutsch,
  日本語, 한국어) or with `export JEV_REPLY_LANGUAGE="Same as message"`. Restart after changing.
- Never put keys in the repo. Never paste a key into an issue.

## Privacy

See [PRIVACY.md](PRIVACY.md). In short: message text stays in memory on your Mac, except the
text you send to the judgment and generation services **you** configure. Logs contain no
message text.

## Limits

- Only the chat open in the focused Messages window is read.
- Images, stickers, links, and attachments come through only as their accessibility text
  (for example "1 image", "Includes picture").
- **Not verified yet:** group chats, replies (threads), tapbacks, edited / unsent messages,
  non-English macOS UI (the `Your iMessage` prefix and time format are English), SMS vs RCS
  sender prefixes. Direction falls back to bubble geometry, which is language-neutral.
- If Apple renames the AX identifiers, update the constants at the top of
  `src/apps/imessage_app.py` (run the probe first).

## License

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Keep both when you redistribute.
This project is not affiliated with Apple.
