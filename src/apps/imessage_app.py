"""Messages.app (iMessage / SMS) adapter: reads the chat through the system accessibility
(AX) tree. No screenshot, no OCR, no chat.db.

Probe facts (2026-10-01, macOS 27.2, English UI; see _reports/imessage-probe_report.md):
- The transcript is an AXGroup with AXIdentifier "TranscriptCollectionView". Each
  message is a full-width AXGroup child whose AXDescription is
  "<sender>, <body>, <time>"; own messages use the sender "Your iMessage".
  Date separators and the "Delivered" line are AXGroups with an empty description.
- The bubble is the first child of the message group (AXIdentifier "Sticker"); its
  frame is the real bubble: incoming bubbles touch the left edge of the chat pane,
  own bubbles touch the right edge.
- Scrolled-out messages stay in the tree with frames outside the window.
- The input is the AXTextField "messageBodyField"; AXValue is settable and reads back.
  The chat title is the AXDescription of the AXButton "ConversationTitle".

Read-only. The one write action is "fill": set AXValue of the input. Never send,
never press Return, never touch the send path.
"""
from __future__ import annotations

import hashlib
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

import AppKit
import ApplicationServices as AS
import Quartz

if __name__ == "__main__" and not __package__:   # CLI self-test: put src/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fill
from perception import Message, WindowInfo

KEY = "imessage"
DISPLAY_NAME = "Messages"
BUNDLE_IDS = ("com.apple.MobileSMS",)
APP_NAMES = ("Messages", "信息")

TRANSCRIPT_ID = "TranscriptCollectionView"
INPUT_ID = "messageBodyField"
ENTRY_ID = "MessageEntryView"
TITLE_ID = "ConversationTitle"
MAX_NODES = 3000
MAX_MESSAGES = 12

# "<sender>, <body>, <time>". The time is "4:35 PM" (U+202F before AM/PM) or "16:35".
_TIME_TAIL = re.compile(r",\s*\d{1,2}[:.]\d{2}(?:\s*[AaPp]\.?[Mm]\.?)?\s*$")
_SELF_PREFIX = re.compile(r"^Your (?:iMessage|text message|SMS|RCS message|message)\s*,\s*", re.I)

ERR_NO_APP = "Messages is not running"
ERR_NO_WINDOW = "No Messages chat window found"
ERR_NO_TRANSCRIPT = "No conversation is open in Messages"

REASON_NO_INPUT = "Could not find the Messages input field"
REASON_UNREADABLE = "Could not read the input field; fill stopped"
REASON_CHANGED = "The input target changed; wait a moment and try again"
REASON_NOT_LANDED = "Wrote to the input field but could not confirm it; check the draft"


class AXReader:
    """Minimal AX read interface; tests replace it with an in-memory tree."""

    def _str(self, el, name) -> str:
        v = fill._ax_attr(el, name)
        return v if isinstance(v, str) else ""

    def role(self, el) -> str:
        return self._str(el, AS.kAXRoleAttribute)

    def ident(self, el) -> str:
        return self._str(el, "AXIdentifier")

    def desc(self, el) -> str:
        return self._str(el, AS.kAXDescriptionAttribute)

    def value_or_none(self, el):
        """AXValue string, or None. An empty Messages input reads as None, not ""."""
        v = fill._ax_attr(el, AS.kAXValueAttribute)
        return v if isinstance(v, str) else None

    def rect(self, el):
        return fill._ax_rect(el)

    def children(self, el) -> list:
        v = fill._ax_attr(el, AS.kAXChildrenAttribute)
        try:
            return list(v or [])
        except TypeError:
            return []

    def windows(self, app_el) -> list:
        v = fill._ax_attr(app_el, AS.kAXWindowsAttribute)
        try:
            return list(v or [])
        except TypeError:
            return []

    def focused_window(self, app_el):
        return fill._ax_attr(app_el, AS.kAXFocusedWindowAttribute)


# ------------------------------------------------------------------ pure parsing

def walk(ax, root, limit: int = MAX_NODES, prune=None):
    """Bounded depth-first walk; prune(el) true keeps el but skips its subtree."""
    stack = [root]
    seen = 0
    while stack and seen < limit:
        el = stack.pop()
        seen += 1
        yield el
        if prune is not None and prune(el):
            continue
        stack.extend(reversed(ax.children(el)))


def find_by_id(ax, root, ident: str, prune_ids=()):
    """First node with this AXIdentifier. Subtrees with an id in prune_ids are skipped
    (the transcript holds hundreds of nodes and never holds the input or title)."""
    def prune(el) -> bool:
        return ax.ident(el) in prune_ids
    for el in walk(ax, root, prune=prune if prune_ids else None):
        if ax.ident(el) == ident:
            return el
    return None


def _intersects(a, b) -> bool:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    return ax0 < bx0 + bw and bx0 < ax0 + aw and ay0 < by0 + bh and by0 < ay0 + ah


def _inside(inner, outer, slack: float = 3.0) -> bool:
    x, y, w, h = inner
    ox, oy, ow, oh = outer
    return (x >= ox - slack and y >= oy - slack
            and x + w <= ox + ow + slack and y + h <= oy + oh + slack)


def parse_desc(desc: str, title: str = "") -> tuple[str | None, str, bool]:
    """(sender, body, is_self) from "<sender>, <body>, <time>".

    The time tail is optional (grouped bubbles can drop it). Senders may contain commas,
    so the chat title is tried as the sender first; otherwise the sender ends at the
    first comma."""
    d = _TIME_TAIL.sub("", (desc or "").strip()).strip()
    m = _SELF_PREFIX.match(d)
    if m:
        return None, d[m.end():].strip(), True
    if title and d.startswith(title + ","):
        return title, d[len(title) + 1:].strip(), False
    sender, sep, body = d.partition(",")
    if not sep:
        return None, d, False
    return sender.strip() or None, body.strip(), False


def side_of(bubble, pane) -> str:
    """'me' when the bubble is nearer the right edge of the chat pane. Compare the two
    edge gaps, not the centre: a long message spans past the middle on both sides."""
    if bubble is None or pane is None:
        return "unknown"
    bx, _, bw, _ = bubble
    px, _, pw, _ = pane
    left_gap = bx - px
    right_gap = (px + pw) - (bx + bw)
    if abs(left_gap - right_gap) < 8:
        return "unknown"
    return "me" if right_gap < left_gap else "them"


def pane_rect(ax, window, entry):
    """Horizontal extent of the chat pane: from the entry bar's left edge to the window's
    right edge (the transcript group itself is full-window wide, sidebar included)."""
    w = ax.rect(window)
    e = ax.rect(entry) if entry is not None else None
    if w is None:
        return None
    if e is None:
        return w
    return (e[0], w[1], w[0] + w[2] - e[0], w[3])


def extract_messages(ax, window, transcript, entry, title: str = "",
                     max_messages: int = MAX_MESSAGES) -> list[Message]:
    """Transcript children -> ordered visible messages (newest last).
    Coordinates are normalised to the window, top origin, like the OCR path."""
    win = ax.rect(window)
    if win is None or transcript is None:
        return []
    wx, wy, ww, wh = win
    pane = pane_rect(ax, window, entry)
    entry_rect = ax.rect(entry) if entry is not None else None
    out: list[Message] = []
    for el in ax.children(transcript):
        desc = ax.desc(el).strip()
        if not desc or ax.role(el) != "AXGroup":
            continue                       # date separators, "Delivered", spacers
        r = ax.rect(el)
        if r is None or r[3] <= 1 or not _inside(r, win):
            continue                       # scrolled out of view
        if entry_rect is not None and _intersects(r, entry_rect):
            continue
        kids = ax.children(el)
        bubble = ax.rect(kids[0]) if kids else None
        sender, body, is_self = parse_desc(desc, title)
        if not body:
            continue
        side = "me" if is_self else side_of(bubble, pane)
        if side == "unknown" and not is_self and sender:
            side = "them"                  # a named sender that is not "Your …"
        bx, by, bw, bh = bubble or r
        ny = (by - wy) / wh
        out.append(Message(text=body, side=side, y=ny, conf=1.0, h=bh / wh,
                           sender=None if side == "me" else sender, lines=[body],
                           x=(bx - wx) / ww, w=bw / ww, last_y=ny))
    out.sort(key=lambda m: m.y)
    return out[-max_messages:]


def fingerprint(title: str, msgs: list[Message]) -> bytes:
    h = hashlib.sha1(title.encode("utf-8"))
    for m in msgs:
        h.update(b"\n" + m.side.encode("ascii") + b"\t" + m.text.encode("utf-8"))
    return h.digest()


# ------------------------------------------------------------------ process and window

def build_app():
    try:
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(BUNDLE_IDS[0])
        if apps and len(apps) > 0:
            return apps[0]
    except Exception:
        pass
    return None


def app_element(pid: int):
    return AS.AXUIElementCreateApplication(pid)


def chat_parts(ax, app_el):
    """(window, transcript, entry, input, title) for the chat window: focused window first,
    then the largest. Windows without a transcript (Settings, empty state) are skipped."""
    cands = []
    for w in ax.windows(app_el):
        transcript = find_by_id(ax, w, TRANSCRIPT_ID)
        if transcript is None:
            continue
        entry = find_by_id(ax, w, ENTRY_ID, prune_ids=(TRANSCRIPT_ID,))
        field = find_by_id(ax, entry, INPUT_ID) if entry is not None else None
        title_el = find_by_id(ax, w, TITLE_ID, prune_ids=(TRANSCRIPT_ID,))
        title = ax.desc(title_el).strip() if title_el is not None else ""
        cands.append((w, transcript, entry, field, title))
    if not cands:
        return None
    focused = ax.focused_window(app_el)
    for c in cands:
        if focused is not None and c[0] == focused:
            return c

    def area(c):
        r = ax.rect(c[0])
        return r[2] * r[3] if r else 0.0
    return max(cands, key=area)


def window_id(pid: int, rect) -> int:
    """CGWindowList id by pid + frame; 0 when not found (does not block reading)."""
    if rect is None:
        return 0
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    try:
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    except Exception:
        return 0
    for wi in wins:
        if int(wi.get("kCGWindowOwnerPID") or 0) != pid:
            continue
        b = dict(wi.get("kCGWindowBounds") or {})
        cand = (float(b.get("X", 0)), float(b.get("Y", 0)),
                float(b.get("Width", 0)), float(b.get("Height", 0)))
        if fill._same_rect(cand, tuple(rect)):
            return int(wi.get("kCGWindowNumber") or 0)
    return 0


def find_window(previous_wid=None, ax=None) -> WindowInfo | None:
    ax = ax or AXReader()
    app = build_app()
    if app is None:
        return None
    pid = app.processIdentifier()
    parts = chat_parts(ax, app_element(pid))
    if parts is None:
        return None
    win, _t, _e, _f, title = parts
    r = ax.rect(win)
    if r is None:
        return None
    return WindowInfo(wid=window_id(pid, r), pid=pid, title=title, x=r[0], y=r[1], w=r[2], h=r[3])


def read_conversation(max_messages: int = MAX_MESSAGES, previous_wid=None,
                      prev_fingerprint=None, prev_layout=None, ax=None) -> dict:
    """One read. Same shape as perception.read_conversation."""
    t0 = time.perf_counter()
    ax = ax or AXReader()
    if not fill.has_accessibility():
        return {"ok": False, "error": fill.REASON_NO_ACCESS, "messages": []}
    app = build_app()
    if app is None:
        return {"ok": False, "error": ERR_NO_APP, "messages": []}
    pid = app.processIdentifier()
    app_el = app_element(pid)
    if not ax.windows(app_el):
        return {"ok": False, "error": ERR_NO_WINDOW, "messages": []}
    parts = chat_parts(ax, app_el)
    if parts is None:
        return {"ok": False, "error": ERR_NO_TRANSCRIPT, "messages": []}
    win, transcript, entry, field, title = parts
    r = ax.rect(win)
    if r is None:
        return {"ok": False, "error": ERR_NO_WINDOW, "messages": []}
    wid = window_id(pid, r)
    window = {"wid": wid, "title": title, "x": r[0], "y": r[1], "w": r[2], "h": r[3]}
    f_rect = ax.rect(field) if field is not None else None
    layout = (wid, r[2], r[3])
    msgs = extract_messages(ax, win, transcript, entry, title=title, max_messages=max_messages)
    fp = fingerprint(title, msgs)
    total = (time.perf_counter() - t0) * 1000
    timing = {"capture": total, "ocr": 0.0, "total": total, "capture_path": "ax"}
    base = {"ok": True, "layout": layout, "input_rect": tuple(f_rect) if f_rect else None,
            "input_unresolved": False, "chat_title": title, "window": window,
            "fingerprint": fp, "timing_ms": timing}
    if layout == prev_layout and fp == prev_fingerprint:
        return dict(base, unchanged=True, messages=[], n_blocks=0)
    return dict(base, unchanged=False, messages=msgs, n_blocks=len(msgs))


# ------------------------------------------------------------------ fill (the one write)

def locate_input(win: dict, ax=None) -> dict:
    """Read-only: the input AXTextField and its screen rect. Same shape as fill.locate_input."""
    result = {"box": None, "rect": None, "window": win, "reason": REASON_NO_INPUT}
    if not fill.has_accessibility():
        result["reason"] = fill.REASON_NO_ACCESS
        return result
    ax = ax or AXReader()
    app = build_app()
    if app is None:
        result["reason"] = ERR_NO_APP
        return result
    parts = chat_parts(ax, app_element(app.processIdentifier()))
    field = parts[3] if parts is not None else None
    if field is None:
        return result
    rect = ax.rect(field)
    if rect is None:
        return result
    vals = [win.get(k) for k in ("x", "y", "w", "h")]
    if any(v is None for v in vals):
        return result
    if not _inside(rect, tuple(float(v) for v in vals)):
        result["reason"] = "The input field is not inside the current chat window"
        return result
    result.update(box=field, rect=tuple(rect), reason="fill target")
    return result


_FILL_LOCK = threading.Lock()
_LAST_FILL: tuple[str, str, float] | None = None


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", s or "") if not c.isspace())


def _landed(before: str, after: str, text: str) -> bool:
    return after != before and _norm(after).endswith(_norm(text))


def fill_text(text: str, target=None, ax=None) -> tuple[bool, str]:
    """Write a candidate into the input field via AXValue and read it back. A draft is kept
    and the text is appended after it. Never sends; no keyboard events; no clipboard."""
    global _LAST_FILL
    text = (text or "").strip()
    if not text:
        return False, fill.REASON_EMPTY
    if not _FILL_LOCK.acquire(blocking=False):
        return False, fill.REASON_BUSY
    try:
        if not fill.has_accessibility():
            return False, fill.REASON_NO_ACCESS
        ax = ax or AXReader()
        if target is None or target.get("box") is None:
            return False, REASON_NO_INPUT
        fresh = locate_input(target["window"], ax=ax)
        field = fresh["box"]
        if (field is None or field != target["box"]
                or not fill._same_rect(fresh["rect"], target["rect"])):
            return False, REASON_CHANGED
        current = ax.value_or_none(field) or ""      # empty field reads as None
        if fill._duplicate_blocked(text, current, _LAST_FILL, time.monotonic()):
            return False, fill.REASON_DUPLICATE
        base = current + " " if current.strip() else ""
        if not fill._ax_set_value(field, base + text):
            return False, fill.REASON_WRITE_FAILED
        landed = ax.value_or_none(field) or ""
        if not _landed(current, landed, text):
            return False, REASON_NOT_LANDED
        _LAST_FILL = (text, landed, time.monotonic())
        return True, "Filled (not sent)"
    finally:
        _FILL_LOCK.release()


class IMessageApp:
    key = KEY
    display_name = DISPLAY_NAME
    bundle_ids = BUNDLE_IDS
    app_names = APP_NAMES
    needs_screen_capture = False

    def find_window(self, previous_wid=None):
        return find_window(previous_wid)

    def read_conversation(self, **kwargs):
        return read_conversation(**kwargs)

    def locate_input(self, win):
        return locate_input(win)

    def fill_text(self, text, target=None):
        return fill_text(text, target=target)

    def warm(self):
        return None


if __name__ == "__main__":
    res = read_conversation()
    if not res["ok"]:
        print("ERROR:", res["error"])
        raise SystemExit(1)
    w = res["window"]
    print(f"window wid={w['wid']} {w['w']:.0f}x{w['h']:.0f} title={res['chat_title']!r} "
          f"ax={res['timing_ms']['total']:.0f}ms n={res['n_blocks']} input={res['input_rect']}")
    print("--- messages (top to bottom) ---")
    for m in res["messages"]:
        print(f"  [{m.side:7s}] y={m.y:.3f} x={m.x:.2f} w={m.w:.2f} sender={m.sender!r} | {m.text}")
