#!/bin/zsh
# Start the jev-imessage panel (no LaunchAgent; start it by hand when needed)
cd "$(dirname "$0")" || exit 1
export USE_TF=0
# uv installs to ~/.local/bin; a Finder-launched .command does not inherit a login shell
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
# same user-level env the .app launcher uses (API keys live outside the repo)
source ./packaging/bootstrap_uv.sh || exit 1
jev_load_env "$HOME/.config/jev-imessage/env"

LOG="$HOME/Library/Logs/jev-imessage.log"
mkdir -p "$(dirname "$LOG")" || exit 1
if ! jev_check_arch; then
    print -r -- "$JEV_ARCH_ERROR"
    print -r -- "Details: $LOG"
    exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
    print "uv not found; installing it now. Progress log: $LOG"
fi
if ! jev_ensure_uv "$LOG"; then
    print -r -- "$JEV_UV_ERROR"
    print -r -- "Details: $LOG. You can also run brew install uv yourself and try again."
    exit 1
fi

exec uv run python src/hud.py
