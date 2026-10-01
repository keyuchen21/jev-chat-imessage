# tests/test_imessage_adapter.py
"""Messages.app adapter: in-memory fake AX tree. No screen, no Messages process, no permission.

Node shapes and frames follow the 2026-10-01 probe on macOS 27.2 (English UI):
window (1299, 463, 1182, 855), entry bar starts at x=1619, own bubbles end at x≈2461.
Run: uv run python -B -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from apps import imessage_app as im


class N:
    def __init__(self, role='AXGroup', ident='', desc='', value=None, rect=None, children=()):
        self.role, self.ident_, self.desc_, self.value = role, ident, desc, value
        self.rect_, self.children_ = rect, list(children)


class FakeAX:
    def __init__(self, windows=(), focused=None):
        self._windows, self._focused = list(windows), focused
    def role(self, el): return el.role
    def ident(self, el): return el.ident_
    def desc(self, el): return el.desc_
    def value_or_none(self, el): return el.value
    def rect(self, el): return el.rect_
    def children(self, el): return el.children_
    def windows(self, app_el): return self._windows
    def focused_window(self, app_el): return self._focused


WIN = (1299.0, 463.0, 1182.0, 855.0)
PANE_X = 1619.0
PANE_R = 2481.0


def bubble(desc, y, side, w=110.0, h=35.0):
    x = PANE_R - 20.0 - w if side == 'me' else PANE_X + 20.0
    return N(desc=desc, rect=(WIN[0], y, WIN[2], h), children=[
        N(ident='Sticker', desc=desc, rect=(x, y, w, h)),
    ])


def stamp(text, y):
    return N(rect=(WIN[0], y, WIN[2], 13.0), children=[
        N('AXStaticText', desc=text, rect=(PANE_X + 20.0, y, 822.0, 13.0)),
    ])


def window(rows, title='Alex', field_value=None):
    field = N('AXTextField', ident='messageBodyField', desc='Message', value=field_value,
              rect=(1677.0, 1276.0, 717.5, 31.0))
    return N('AXWindow', rect=WIN, children=[
        N(rect=WIN, children=[
            N(ident='CKConversationListCollectionView', rect=(WIN[0], WIN[1], 320.0, WIN[3])),
            N(rect=WIN, children=[
                N(ident='TranscriptCollectionView', desc='Messages', rect=WIN, children=rows),
                N(ident='MessageEntryView', rect=(PANE_X, 1276.0, 862.0, 42.0), children=[
                    N('AXButton', desc='add'), field]),
            ]),
            N('AXButton', ident='ConversationTitle', desc=title),
        ]),
    ])


class ParseDescTests(unittest.TestCase):
    def test_self_message(self):
        self.assertEqual(im.parse_desc('Your iMessage, See you at 8!, 4:35 PM'),
                         (None, 'See you at 8!', True))

    def test_self_sms(self):
        self.assertEqual(im.parse_desc('Your text message, ok, 9:01 AM'), (None, 'ok', True))

    def test_incoming_with_commas_in_body(self):
        self.assertEqual(im.parse_desc('Alex, yes, see you then, 12:39 PM'),
                         ('Alex', 'yes, see you then', False))

    def test_sender_with_comma_uses_title(self):
        self.assertEqual(im.parse_desc('Lee, Ann, hi, 16:35', title='Lee, Ann'),
                         ('Lee, Ann', 'hi', False))

    def test_chinese_body_is_kept(self):
        self.assertEqual(im.parse_desc('+1 (555) 010-0199, 好的，明天见🙏, 9:22 PM'),
                         ('+1 (555) 010-0199', '好的，明天见🙏', False))

    def test_no_time_tail(self):
        self.assertEqual(im.parse_desc('Alex, hello'), ('Alex', 'hello', False))


class SideTests(unittest.TestCase):
    PANE = (PANE_X, WIN[1], PANE_R - PANE_X, WIN[3])

    def test_right_bubble_is_me(self):
        self.assertEqual(im.side_of((2350.5, 0, 110.5, 35), self.PANE), 'me')

    def test_left_bubble_is_them(self):
        self.assertEqual(im.side_of((PANE_X + 20, 0, 487, 51), self.PANE), 'them')

    def test_long_bubble_uses_edge_gaps_not_centre(self):
        # 700 of 862 wide: the centre is right of the middle, but it touches the left edge
        self.assertEqual(im.side_of((PANE_X + 20, 0, 700, 51), self.PANE), 'them')

    def test_missing_geometry_is_unknown(self):
        self.assertEqual(im.side_of(None, self.PANE), 'unknown')


class ExtractTests(unittest.TestCase):
    def read(self, rows, **kw):
        w = window(rows, **kw)
        ax = FakeAX([w], focused=w)
        win, transcript, entry, field, title = im.chat_parts(ax, None)
        return im.extract_messages(ax, win, transcript, entry, title=title)

    def test_order_sides_and_bodies(self):
        msgs = self.read([
            stamp('Today 4:35 PM', 950.0),
            bubble('Alex, are you coming?, 4:30 PM', 980.0, 'them', w=200),
            bubble('Your iMessage, See you at 8!, 4:35 PM', 1214.0, 'me'),
            stamp('Delivered', 1248.0),
        ])
        self.assertEqual([(m.side, m.sender, m.text) for m in msgs],
                         [('them', 'Alex', 'are you coming?'), ('me', None, 'See you at 8!')])

    def test_scrolled_out_messages_are_dropped(self):
        msgs = self.read([
            bubble('Your iMessage, old one, 12:39 PM', 221.0, 'me', h=720.0),
            bubble('Alex, new one, 4:30 PM', 980.0, 'them'),
        ])
        self.assertEqual([m.text for m in msgs], ['new one'])

    def test_group_sender_names(self):
        msgs = self.read([
            bubble('Ann, lunch?, 1:00 PM', 900.0, 'them'),
            bubble('Bob, sure, 1:01 PM', 950.0, 'them'),
        ], title='Ann & Bob')
        self.assertEqual([(m.sender, m.text) for m in msgs], [('Ann', 'lunch?'), ('Bob', 'sure')])

    def test_keeps_the_newest(self):
        rows = [bubble(f'Alex, m{i}, 1:00 PM', 500.0 + i * 40, 'them') for i in range(18)]
        msgs = self.read(rows)
        self.assertEqual(len(msgs), im.MAX_MESSAGES)
        self.assertEqual(msgs[-1].text, 'm17')

    def test_window_without_transcript_is_skipped(self):
        settings = N('AXWindow', rect=(0, 0, 600, 400))
        self.assertIsNone(im.chat_parts(FakeAX([settings]), None))


class FillTests(unittest.TestCase):
    def setUp(self):
        im._LAST_FILL = None
        self.w = window([bubble('Alex, hi, 1:00 PM', 980.0, 'them')])
        self.ax = FakeAX([self.w], focused=self.w)
        self.field = im.chat_parts(self.ax, None)[3]
        self.win = dict(zip('xywh', WIN))
        app = type('App', (), {'processIdentifier': lambda self: 1})()
        self.patches = [patch.object(im, 'build_app', return_value=app),
                        patch.object(im.fill, 'has_accessibility', return_value=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def set_value(self, writes):
        def fake(el, text):
            writes.append(text)
            el.value = text
            return True
        return patch.object(im.fill, '_ax_set_value', side_effect=fake)

    def target(self):
        return im.locate_input(self.win, ax=self.ax)

    def test_fills_empty_field(self):
        writes = []
        with self.set_value(writes):
            ok, _ = im.fill_text('See you at 5', target=self.target(), ax=self.ax)
        self.assertTrue(ok)
        self.assertEqual(writes, ['See you at 5'])

    def test_appends_after_draft(self):
        self.field.value = 'Hey'
        writes = []
        with self.set_value(writes):
            ok, _ = im.fill_text('see you at 5', target=self.target(), ax=self.ax)
        self.assertTrue(ok)
        self.assertEqual(writes, ['Hey see you at 5'])

    def test_refused_write_reports_failure(self):
        with patch.object(im.fill, '_ax_set_value', return_value=False):
            ok, reason = im.fill_text('x', target=self.target(), ax=self.ax)
        self.assertFalse(ok)
        self.assertEqual(reason, im.fill.REASON_WRITE_FAILED)

    def test_moved_field_is_refused(self):
        t = self.target()
        t['rect'] = (0.0, 0.0, 10.0, 10.0)
        ok, reason = im.fill_text('x', target=t, ax=self.ax)
        self.assertFalse(ok)
        self.assertEqual(reason, im.REASON_CHANGED)

    def test_no_target(self):
        self.assertEqual(im.fill_text('x', target=None, ax=self.ax), (False, im.REASON_NO_INPUT))


if __name__ == '__main__':
    unittest.main()
