# tests/test_registry.py
"""apps adapter layer: the registry dispatches by bundle id / name to the Messages adapter.

Run: uv run python -B -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


class RegistryTests(unittest.TestCase):
    def test_messages_by_bundle_id(self):
        from apps import registry
        with patch.object(registry, '_frontmost', return_value=('com.apple.MobileSMS', 'Some Name')):
            self.assertEqual(registry.frontmost_app().key, 'imessage')

    def test_messages_by_name(self):
        from apps import registry
        for name in ('Messages', '信息'):
            with patch.object(registry, '_frontmost', return_value=('', name)):
                self.assertEqual(registry.frontmost_app().key, 'imessage', name)

    def test_other_apps_are_not_chat_apps(self):
        from apps import registry
        for bundle, name in (('com.google.Chrome', 'Google Chrome'), ('com.tencent.xinWeChat', '微信'),
                             ('com.tencent.qq', 'QQ'), ('', 'Messenger')):
            with patch.object(registry, '_frontmost', return_value=(bundle, name)):
                self.assertIsNone(registry.frontmost_app(), (bundle, name))

    def test_query_failure_is_unknown_not_none(self):
        from apps import registry
        with patch.object(registry, '_frontmost', return_value=None):
            self.assertIs(registry.frontmost_app(), registry.UNKNOWN)

    def test_workspace_exception_is_unknown(self):
        from apps import registry
        with patch('AppKit.NSWorkspace') as ws:      # PyObjC selectors cannot be patched directly
            ws.sharedWorkspace.side_effect = RuntimeError
            self.assertIs(registry.frontmost_app(), registry.UNKNOWN)

    def test_app_by_key(self):
        from apps import registry
        self.assertEqual(registry.app_by_key('imessage').display_name, 'Messages')
        self.assertIsNone(registry.app_by_key('wechat'))
        self.assertEqual([a.key for a in registry.APPS], ['imessage'])
        self.assertFalse(registry.APPS[0].needs_screen_capture)


if __name__ == '__main__':
    unittest.main()
