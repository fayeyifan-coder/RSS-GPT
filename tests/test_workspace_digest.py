import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from workspace_digest import public_item, write_public_digest


class WorkspaceDigestTests(unittest.TestCase):
    def test_public_record_is_text_only_with_stable_id(self):
        item = public_item("国际新闻", "BBC", "中文标题", "新闻摘要", "https://example.org/story")
        self.assertIsNotNone(item)
        self.assertEqual(item["category"], "国际新闻")
        self.assertEqual(len(item["id"]), 64)
        self.assertEqual(set(item), {"id", "category", "source", "title", "summary", "url"})
        self.assertEqual(item, public_item("国际新闻", "BBC", "中文标题", "新闻摘要", "https://example.org/story"))

    def test_unsafe_link_and_unknown_category_are_not_published(self):
        for link in ["javascript:alert(1)", "http://example.org/story", "https://user:pass@example.org/", "https://example.org/a\nb", "https://example.org/a b"]:
            self.assertIsNone(public_item("国际新闻", "BBC", "标题", "摘要", link))
        self.assertIsNone(public_item("私人内容", "BBC", "标题", "摘要", "https://example.org/"))

    def test_atomic_snapshot_deduplicates_and_preserves_last_success_on_empty(self):
        item = public_item("生态与鸟类", "Nature", "鸟类论文", "新的发现", "https://example.org/birds")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-digest.json"
            when = datetime(2026, 10, 31, 0, 15, tzinfo=timezone.utc)
            self.assertTrue(write_public_digest([item, item], path, when))
            original = path.read_bytes()
            data = json.loads(original)
            self.assertEqual(data["schemaVersion"], 1)
            self.assertEqual(data["reportDate"], "2026-10-31")
            self.assertEqual(data["generatedAt"], "2026-10-31T00:15:00Z")
            self.assertEqual(len(data["items"]), 1)
            self.assertFalse(write_public_digest([], path, when))
            self.assertEqual(path.read_bytes(), original)

    def test_does_not_create_empty_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-digest.json"
            self.assertFalse(write_public_digest([], path))
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
