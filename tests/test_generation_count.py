"""Candidate-count configuration and prompt regressions."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate
import settings_config
import styles


class CandidateCountConfigTests(unittest.TestCase):
    def test_settings_persist_candidate_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            updated = settings_config.write_settings(
                path, "", {"JEV_CANDIDATES_PER_TONE": "4"})
            self.assertIn("export JEV_CANDIDATES_PER_TONE=4", updated)

    def test_settings_reject_candidate_count_outside_supported_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            for value in ("0", "6", "not-a-number"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    settings_config.write_settings(
                        path, "", {"JEV_CANDIDATES_PER_TONE": value})
            self.assertFalse(path.exists())


class CandidateCountGenerationTests(unittest.TestCase):
    def test_one_candidate_uses_single_candidate_instructions(self):
        generator = generate.Generator()
        with patch.object(styles, "PER_TONE", 1), \
             patch.object(styles, "REPLY_LANGUAGE", styles.SAME_LANGUAGE), \
             patch.object(generator, "_call", return_value="只给一条回复") as call:
            texts, error = generator._one_tone("current message", "Small talk", "Warm & tactful")

        self.assertEqual((texts, error), (["只给一条回复"], ""))
        prompt = call.call_args.args[0]
        self.assertIn("Write 1 reply candidates", prompt)
        self.assertIn("Write one safe reply", prompt)
        self.assertNotIn("The first is safe", prompt)
        self.assertIn("same language as the message", prompt)

    def test_multiple_candidates_are_limited_to_configured_count(self):
        generator = generate.Generator()
        response = "第一条\n第二条\n第三条\n第四条"
        with patch.object(styles, "PER_TONE", 3), \
             patch.object(generator, "_call", return_value=response) as call:
            texts, error = generator._one_tone("current message", "Small talk", "Warm & tactful")

        self.assertEqual((texts, error), (["第一条", "第二条", "第三条"], ""))
        prompt = call.call_args.args[0]
        self.assertIn("Write 3 reply candidates", prompt)
        self.assertIn("Output exactly 3 lines", prompt)
        self.assertIn("The first is safe", prompt)


class ReplyLanguageTests(unittest.TestCase):
    def prompt(self, language):
        generator = generate.Generator()
        with patch.object(styles, "REPLY_LANGUAGE", language), \
             patch.object(generator, "_call", return_value="ok") as call:
            generator._one_tone("你好", "Small talk", "Warm & tactful")
        return call.call_args.args[0]

    def test_default_is_english(self):
        self.assertEqual(styles.reply_language(None), "English")
        self.assertEqual(styles.reply_language("Klingon"), "English")

    def test_english_is_stated_twice_and_overrides_message_language(self):
        prompt = self.prompt("English")
        self.assertEqual(prompt.count("Write every reply in English only"), 2)
        self.assertNotIn("same language as the message", prompt)

    def test_named_language(self):
        self.assertIn("Write every reply in Simplified Chinese only", self.prompt("简体中文"))

    def test_same_as_message(self):
        self.assertIn("same language as the message", self.prompt(styles.SAME_LANGUAGE))

    def test_settings_persist_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            updated = settings_config.write_settings(path, "", {"JEV_REPLY_LANGUAGE": "日本語"})
            self.assertIn("JEV_REPLY_LANGUAGE=", updated)
            self.assertIn("日本語", updated)
            with self.assertRaises(ValueError):
                settings_config.write_settings(path, updated, {"JEV_REPLY_LANGUAGE": "Klingon"})


if __name__ == "__main__":
    unittest.main()
