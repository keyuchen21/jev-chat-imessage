#!/usr/bin/env python3
"""Messages.app AX probe: print the transcript nodes, bubble frames, side, title and input.

Usage (a chat open in Messages):
    uv run python probe/imessage_probe.py            # read only; message text is masked
    uv run python probe/imessage_probe.py --show     # print the full descriptions
    uv run python probe/imessage_probe.py --fill hi  # also set the input once, read back, clear

Never sends, never presses keys, never uses the clipboard. --fill runs only when the
input is empty, and clears it again after reading back.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ApplicationServices as AS

from apps import imessage_app as im


def mask(s: str, show: bool) -> str:
    if show or len(s) < 30:
        return s
    return s[:18] + f" …({len(s)} chars)… " + s[-12:]


def main() -> int:
    show = "--show" in sys.argv
    fill_text = None
    if "--fill" in sys.argv:
        i = sys.argv.index("--fill")
        if i + 1 >= len(sys.argv):
            print("usage: imessage_probe.py [--show] [--fill TEXT]")
            return 2
        fill_text = sys.argv[i + 1]
    print("AX trusted:", AS.AXIsProcessTrusted())
    app = im.build_app()
    if app is None:
        print("Messages is not running")
        return 1
    ax = im.AXReader()
    app_el = im.app_element(app.processIdentifier())
    wins = ax.windows(app_el)
    print(f"AX windows: {len(wins)}")
    parts = im.chat_parts(ax, app_el)
    if parts is None:
        print("no window with TranscriptCollectionView")
        return 1
    win, transcript, entry, field, title = parts
    pane = im.pane_rect(ax, win, entry)
    print(f"window={ax.rect(win)} entry={ax.rect(entry) if entry else None} pane={pane}")
    print(f"title={title!r} input={ax.rect(field) if field else None} "
          f"value={ax.value_or_none(field) if field else None!r}")
    print("--- transcript children ---")
    for el in ax.children(transcript):
        desc = ax.desc(el)
        kids = ax.children(el)
        b = ax.rect(kids[0]) if kids else None
        kid = f"{ax.role(kids[0])}#{ax.ident(kids[0])}" if kids else "-"
        sub = ax.desc(kids[0]) if kids and not desc else ""
        print(f"  {ax.role(el)} rect={ax.rect(el)} first={kid} bubble={b} "
              f"side={im.side_of(b, pane) if desc else '-'} desc={mask(desc or sub, show)!r}")
    print("--- parsed (visible only) ---")
    for m in im.extract_messages(ax, win, transcript, entry, title=title):
        print(f"  [{m.side:7s}] y={m.y:.3f} sender={m.sender!r} | {mask(m.text, show)}")
    if fill_text is not None and field is not None:
        if ax.value_or_none(field):
            print("--fill skipped: the input has a draft")
        else:
            err = AS.AXUIElementSetAttributeValue(field, AS.kAXValueAttribute, fill_text)
            time.sleep(0.3)
            print(f"--fill set err={err} readback={ax.value_or_none(field)!r}")
            AS.AXUIElementSetAttributeValue(field, AS.kAXValueAttribute, "")
            time.sleep(0.3)
            print(f"--fill cleared readback={ax.value_or_none(field)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
