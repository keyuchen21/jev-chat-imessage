"""Custom-tone loading gate (JEV_TONES quality floor). Offline, no screen, no API."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import styles


class CustomToneTests(unittest.TestCase):
    def setUp(self):
        styles.REJECTED_TONES.clear()

    def tearDown(self):
        styles.REJECTED_TONES.clear()

    def test_short_description_is_refused_with_reason(self):
        with patch.object(styles.userconfig, 'get',
                          return_value='夸我=夸我|好的=嗯'):
            out = styles._custom_tones()
        self.assertNotIn('夸我', out)
        self.assertNotIn('好的', out)
        self.assertTrue(any('"夸我" has only 2 characters' in r for r in styles.REJECTED_TONES))

    def test_well_formed_tone_loads_and_overrides_builtin(self):
        desc = '像个资深摸鱼选手，把活推得很得体又不失礼'
        with patch.object(styles.userconfig, 'get',
                          return_value=f'摸鱼大师={desc}|Witty=dry humour, one clever twist, never mean to them'):
            out = styles._custom_tones()
        self.assertEqual(out['摸鱼大师'], desc)
        self.assertIn('Witty', out)        # same name overrides the built-in
        self.assertEqual(styles.REJECTED_TONES, [])

    def test_exactly_at_floor_loads(self):
        with patch.object(styles.userconfig, 'get',
                          return_value='测试语气=这一句刚好十个字了吗'):
            out = styles._custom_tones()
        self.assertIn('测试语气', out)
        self.assertEqual(styles.REJECTED_TONES, [])

    def test_empty_description_is_refused_not_dropped_silently(self):
        with patch.object(styles.userconfig, 'get', return_value='空说明='):
            out = styles._custom_tones()
        self.assertNotIn('空说明', out)
        self.assertEqual(len(styles.REJECTED_TONES), 1)


class StripLabelTests(unittest.TestCase):
    """strip_label holds for every built-in tone: adding a label only edits BUILTIN (#70)."""

    def test_every_builtin_label_strips_from_its_echo(self):
        for name in styles.BUILTIN:
            for echoed in (f"{name}: sure, see you then", f"{name}：sure, see you then"):
                self.assertEqual(styles.strip_label(echoed), "sure, see you then",
                                 msg=f"label {name!r} not stripped")

    def test_spaces_are_optional_in_echo(self):
        self.assertEqual(styles.strip_label("Short&clear: By 3pm."), "By 3pm.")
        self.assertEqual(styles.strip_label("**Polite decline**: Can't this week, sorry."),
                         "Can't this week, sorry.")

    def test_plain_reply_is_not_touched(self):
        self.assertEqual(styles.strip_label("Sure: let's do 7"), "Sure: let's do 7")
        self.assertEqual(styles.strip_label("先心疼两句，你今天是不是被会灌满了"),
                         "先心疼两句，你今天是不是被会灌满了")


class BuiltinToneTests(unittest.TestCase):
    def test_every_builtin_passes_the_quality_floor(self):
        for name, desc in styles.BUILTIN.items():
            self.assertGreaterEqual(len(desc), styles.MIN_TONE_DESC_CHARS, name)

    def test_default_slots_are_builtin_labels(self):
        self.assertEqual(styles.DEFAULT_SLOTS, ["Warm & tactful", "Friendly casual", "Short & clear"])
        for name in styles.DEFAULT_SLOTS:
            self.assertIn(name, styles.labels())
        self.assertNotIn(styles.NONE_LABEL, styles.BUILTIN)


if __name__ == '__main__':
    unittest.main()
