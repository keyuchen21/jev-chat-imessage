# iMessage probe report (2026-10-01)

Machine: macOS 27.2 (26B5091g), Apple Silicon, English UI. Messages.app running.
Terminal has Accessibility permission (`AX trusted: True`). Contact names, numbers and
message text below are replaced with `<contact>`, `<number>`, `<text>`.

## Questions and answers

| Question | Answer | Evidence |
|---|---|---|
| Is message text in the AX tree? | **Yes.** In the `AXDescription` of each message group: `<sender>, <body>, <time>` | dump 1, 2 |
| Can we tell me from them? | **Yes, two ways.** Own: description starts with `Your iMessage, `. Geometry: own bubble ends ~20 pt from the pane's right edge; incoming bubble starts ~20 pt from the pane's left edge | dump 2, 3 |
| Can we write the input? | **Yes.** `messageBodyField` (AXTextField): `AXValue` settable, readback equal; set back to `""` reads `None` | fill test |
| Need chat.db (route A) or OCR (route C)? | **No** for normal text messages. Route B (AX) only | — |

## Method

Ad-hoc scripts in `/tmp`, then the same checks as `probe/imessage_probe.py` in this repo.
Read-only, except the fill test, which writes only to an empty input and clears it.
Nothing was sent.

## Dump 1 — tree shape (incoming SMS chat, abbreviated)

```
AXWindow/AXStandardWindow id=SceneWindow title=<number>
  AXGroup/iOSContentGroup
    … AXGroup id=CKConversationListCollectionView
        AXTextField/AXSearchField desc=Search
    … AXGroup id=ConversationList desc=Conversations
        AXStaticText desc=<contact>, Pinned
        AXStaticText desc=<number>, <text>…            (sidebar rows: name + preview)
    … AXGroup id=TranscriptCollectionView desc=Messages
        AXGroup desc=<number>, Includes picture, 11:…
          AXButton id=Sticker desc=(same)
          AXButton desc=Save photo
        AXGroup desc=<number>, <text>…
          AXLink id=Sticker desc=(same)
        AXStaticText                                    (spacer, empty)
        AXGroup
          AXStaticText desc=Mon, Sep 7 at 11:01 AM      (date separator: group desc empty)
        …
      AXGroup id=MessageEntryView
        AXButton desc=add
        AXTextField id=messageBodyField desc=Message
        AXButton desc=Record audio
        AXButton desc=Emoji picker
    AXButton id=ConversationTitle desc=<number> val=Show Conversation Details
  AXToolbar …
```

## Dump 2 — incoming bubbles, frames (SMS chat; window x=311, w=1182)

```
transcript (311, 332, 1182, 855)
AXGroup (311, 1074, 1182, 46) '<number>, <text>, 1:30 PM'
   AXLink Sticker (651, 1074, 487, 51)
input (689, 1145, 718, 31) val= None settable= (0, True)
```

Pane left = entry bar x = 631 (window x + 320). Incoming bubble x = 651: left gap 20,
right gap 355 → `them`.

## Dump 3 — own bubbles (1:1 iMessage chat; window (1299, 463, 1182, 855))

`uv run python probe/imessage_probe.py` (text masked by the script):

```
AX trusted: True
AX windows: 1
window=(1299.0, 463.0, 1182.0, 855.0) entry=(1619.0, 1276.0, 862.0, 42.0) pane=(1619.0, 463.0, 862.0, 855.0)
title='<contact>' input=(1677.0, 1276.0, 717.5, 31.0) value=None
--- transcript children ---
  AXGroup rect=(1299.0, 221.0, 1182.0, 715.5) first=AXLink#Sticker bubble=(2111.0, 221.0, 350.0, 720.5) side=me desc='Your iMessage, <text> …(141 chars)… ge, 12:39 PM'
  AXGroup rect=(1299.0, 950.0, 1182.0, 13.0) first=AXStaticText# bubble=(1639.0, 950.0, 822.0, 13.0) side=- desc='Today 4:35 PM'
  AXGroup rect=(1299.0, 968.0, 1182.0, 243.5) first=AXLink#Sticker bubble=(2111.0, 968.0, 350.0, 248.5) side=me desc='Your iMessage, <text> …(184 chars)… age, 4:35 PM'
  AXGroup rect=(1299.0, 1214.0, 1182.0, 30.0) first=AXGroup#Sticker bubble=(2350.5, 1214.0, 110.5, 35.088750000000005) side=me desc='Your iMessage, <text> …(38 chars)… !!!, 4:35 PM'
  AXGroup rect=(1299.0, 1248.0, 1182.0, 12.0) first=AXStaticText# bubble=(2398.0, 1248.0, 47.0, 12.0) side=- desc='Delivered'
--- parsed (visible only) ---
  [me     ] y=0.591 sender=None | <text> …(160 chars)… com, 1 image
  [me     ] y=0.878 sender=None | <text>
```

Notes:
- The first message (y=221) is above the window top (463): scrolled out but still in the
  tree. The parser drops it.
- "Delivered" and date separators are groups with an empty description; skipped.
- Link previews / images appear as text: `…, 1 image`, `Includes picture`, `Image attached`.

## Fill test (empty input in the 1:1 chat)

```
before None placeholder iMessage
set err 0 readback 'jev probe test 测试'
clear err 0 readback None
```

## Adapter CLI on the same chat

`uv run python src/apps/imessage_app.py`:

```
window wid=668 1182x855 title='<contact>' ax=212ms n=2 input=(1677.0, 1276.0, 717.5, 31.0)
--- messages (top to bottom) ---
  [me     ] y=0.591 x=0.69 w=0.30 sender=None | <text>…
  [me     ] y=0.878 x=0.89 w=0.09 sender=None | <text>
```

## What changed (vs. jev-chat-jarvis-mac)

- New `src/apps/imessage_app.py`: AX read (`chat_parts`, `extract_messages`, `parse_desc`,
  `side_of`), fill (AXValue set + readback, append after a draft, no key events).
- `src/apps/registry.py`: `APPS = (IMessageApp(),)`. `src/apps/base.py`: comments.
- Removed: `src/apps/capture_app.py` (WeChat), `src/apps/ax_app.py` (QQ),
  `probe/ax_probe.py`, `tests/test_ax_adapter.py`, org issue bots, WeChat docs/images.
- New `probe/imessage_probe.py`, `tests/test_imessage_adapter.py`; rewrote
  `tests/test_registry.py`.
- `src/hud.py`: calibration button hidden and calibration menu items removed (no capture
  region for an AX-only app).
- English README / AGENTS / CONTRIBUTING / NOTICE / PRIVACY / templates; CI branch
  `master` → `main`; `pyproject.toml` name `jev-chat-imessage`, version 0.1.0, `uv lock`.
- English UI and prompts:
  - `src/hud.py`, `start.command`, `packaging/*`: panel, menus, dialogs, user-facing errors.
  - `src/settings*.py`, `src/userconfig.py`, `src/calibration_ui.py`: settings window.
  - `src/styles.py`: 10 new English tones; defaults: Warm & tactful, Friendly casual,
    Short & clear.
  - `src/generate.py`: English prompt; replies in the language of the incoming message.
  - `src/judge.py`, `src/judge_jev.py`: English intents, risk levels, actions, Jev
    questions.
  - `src/fill.py`, `src/chat_context.py`, `src/perception.py`: reasons and labels.
  - Log lines and code comments stay in Chinese.
- Panel and settings were rendered to PNG and checked. Cut-off labels were fixed:
  `rank…`, Low/Med/High, `● Watch 4/9`, and the shorter tab titles and Jev hint.

## Test output (final)

```
$ uv run --quiet python -B -m unittest discover -s tests
Ran 257 tests in 3.674s
OK
$ uv run --quiet python probe/settings_smoke.py
PASS: native controls, model requests, unified save, chat drafts, validation, partial-save retry, clear history, external file refresh, draft preservation, corrupt-file recovery, environment priority, restart isolation, shell-expression preservation
$ uv run --quiet python probe/bootstrap_regression.py
OK
$ coverage report --fail-under=49
TOTAL                         5330   2490    53%
```

257 = 299 − 38 removed bot tests (issue triage / sub-issue autoclose) − 4 from the rewritten
`test_styles.py`.

## Live run (2026-10-01, built-in generation key, judge skipped)

Started with `JUDGE_BACKEND=skip ./start.command`: no Jev key, local model not downloaded,
no download started. Generation: built-in channel, `glm-4-flash`.

- First run: the panel read the chat and showed 6 candidates. **Problem:** most candidates
  were Chinese for an English message. `glm-4-flash` ignored "same language as the message".
- Fix: new setting `JEV_REPLY_LANGUAGE` (default English; menu in Settings › Replies ·
  OpenAI). The prompt states the language rule twice.
- CLI check after the fix (real output):

```
== language: English
'<real incoming English message, redacted>' -> ["I get it, it's always good to know. I'll check and let you know soon!", "Their team's decent, but there's always room for more!"]
'你周末有空吗？一起吃饭' -> ['Sure, sounds great! How about Saturday at 7 PM?', "Absolutely, let's do it! Sunday at 6:30, what do you think?"]
== language: Same as message
'<real incoming English message, redacted>' -> ["I get it, <name>'s team pretty solid. Let's check their latest project.", "Their team's top-notch, but they're swamped. I'll ask if they can help."]
'你周末有空吗？一起吃饭' -> ['周末确实挺忙的，改天可以吗？下周二晚上有空吗？']
```

- Second run: the owner confirmed on screen that the candidates are English, and that
  clicking Fill put the text into the Messages input field without sending it.
- Log (stage timings only, no text):

```
[18:53:41] 启动 · 判断层 本地 decider-2b · 生成层 http://101.132.131.220:11111/v1 / glm-4-flash (built-in default)
[18:53:57] 生成 2533ms · 3 个话术并发 → 6 条候选
[18:53:57] 端到端 1329ms · 从分析开始到候选上屏
[18:54:35] 生成 4095ms · 3 个话术并发 → 6 条候选
[18:54:35] 端到端 3705ms · 从分析开始到候选上屏
```

AX read: 124–144 ms per read.

## Verification gaps

- **Incoming iMessage in a 1:1 chat**: seen only in an SMS chat (sender = number). An
  iMessage contact's incoming message format is assumed to be `<name>, <body>, <time>`.
- **Group chats, replies/threads, tapbacks, edited/unsent messages, audio messages**: not
  probed.
- **Non-English macOS UI**: the `Your iMessage` prefix and time format not checked; geometry
  fallback should still work.
- **SMS own-message prefix** (`Your text message`?) and RCS: assumed, not seen.
- **Judgment layer in the live run**: not exercised (no Jev key, local model not
  downloaded). Intent, risk, and ranking were not shown on screen.
- **OCR fallback (route C)** when the tree has no text: not wired; never needed on this
  machine.
- **Revoked Accessibility**: the adapter returns `fill.REASON_NO_ACCESS`; not tested by
  turning the permission off.
- **English judge prompts against a real model**: never run. Jev answers on the English
  questions and the local judge accuracy are unmeasured. The 86.4% figure was for the old Chinese prompt.
  `judge_zh_test.py` was not run.
- **`.app` build** (`packaging/build_app.sh`): not built.
- **Built-in relay key** in `src/builtin.py` (from the source repo): kept by owner
  decision (2026-10-01).
- Paths are separate from jev-chat-jarvis-mac (owner decision): `~/.config/jev-imessage/env`,
  `~/Library/Application Support/jev-imessage/`, `~/Library/Logs/jev-imessage.log`,
  `jev-imessage.app`, bundle id `info.jevimessage.app`.
