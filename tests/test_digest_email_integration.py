"""Integration contract: published JSON and outgoing email reuse the same digest.

No network calls, secrets or real email delivery in these tests.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import rss_digest
from workspace_digest import write_public_digest


class OneDigestRunTests(unittest.TestCase):
    def test_public_json_uses_same_summary_as_existing_email_and_no_secret(self):
        entries = [dict(
            title="Bird ecology update",
            link="https://example.org/birds",
            summary="<p>New ecological study.</p>",
        )]
        fake_feed = SimpleNamespace(entries=entries)
        sent = []
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "daily-digest.json"

            def write(items):
                return write_public_digest(items, destination=output)

            with patch.object(rss_digest, "RSS_CATEGORIES", {"🌿 生态与鸟类": {"Nature Ecology": "https://example.org/feed"}}), \
                 patch.object(rss_digest.feedparser, "parse", return_value=fake_feed), \
                 patch.object(rss_digest, "summarize_with_ai", return_value="<h4>中文鸟类新闻</h4><p>中文研究摘要。</p>"), \
                 patch.object(rss_digest, "send_email", side_effect=lambda subject, html: sent.append((subject, html))), \
                 patch.object(rss_digest, "write_public_digest", side_effect=write):
                rss_digest.main()

            self.assertEqual(len(sent), 1)
            self.assertIn("中文鸟类新闻", sent[0][1])
            self.assertIn("中文研究摘要。", sent[0][1])
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(data["items"]), 1)
            item = data["items"][0]
            self.assertEqual(item["title"], "中文鸟类新闻")
            self.assertEqual(item["summary"], "中文研究摘要。")
            self.assertEqual(item["category"], "生态与鸟类")
            self.assertEqual(item["url"], "https://example.org/birds")
            self.assertEqual(set(item), {"id", "category", "source", "title", "summary", "url"})

    def test_export_failure_does_not_block_mail(self):
        with patch.object(rss_digest, "RSS_CATEGORIES", {"🌍 国际新闻": {"BBC": "https://example.org/feed"}}), \
             patch.object(rss_digest.feedparser, "parse", return_value=SimpleNamespace(entries=[dict(
                 title="World headline", link="https://example.org/news", summary="A summary",
             )])), \
             patch.object(rss_digest, "summarize_with_ai", return_value="<h4>全球新闻</h4><p>事件摘要</p>"), \
             patch.object(rss_digest, "write_public_digest", side_effect=OSError("synthetic disk failure")), \
             patch.object(rss_digest, "send_email") as mail:
            rss_digest.main()
        mail.assert_called_once()


if __name__ == "__main__":
    unittest.main()
