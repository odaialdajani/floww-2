import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services import public_release_watch as watch


class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    def test_navigation_and_scripts_do_not_change_content_fingerprint(self):
        content = 'Documented market data response and parameter definitions. ' * 4
        first = watch.Documentation()
        first.feed(f'<nav>old</nav><main>{content}<script>bad()</script></main>')
        second = watch.Documentation()
        second.feed(f'<nav>new</nav><main>{content}</main><script>changed()</script>')
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_new_and_changed_operations_require_review(self):
        old = '/api/docs/resources/market-data/get-quotes'
        new = '/api/docs/resources/market-data/new-feed'
        baseline = {'reviewed_at': '2026-09-26T19:00:00+00:00', 'documents': {watch.CHANGELOG: 'old', old: 'same'}}
        result = watch.compare_documents(baseline, {
            watch.CHANGELOG: {'sha256': 'changed', 'resources': [old, new]},
            old: {'sha256': 'same'},
        })
        self.assertEqual(result['status'], 'review_needed')
        self.assertEqual(result['new_operations'], [new])
        self.assertFalse(result['automatic_activation'])

    def test_empty_baseline_cannot_report_current(self):
        with self.assertRaises(ValueError):
            watch.compare_documents({'documents': {}}, {})

    def test_streamed_document_body_is_read_without_running_scripts(self):
        text = 'Actual published documentation. ' * 10
        streamed = watch.Documentation()
        streamed.feed(f'<main></main><div hidden id="S:0"><div>{text}</div></div><script>hydrate()</script>')
        regular = watch.Documentation()
        regular.feed(f'<main>{text}</main>')
        self.assertEqual(streamed.fingerprint(), regular.fingerprint())

    def test_empty_or_error_page_cannot_be_verified(self):
        parser = watch.Documentation()
        parser.feed('<main>Temporarily unavailable</main>')
        with self.assertRaises(ValueError):
            parser.fingerprint()

    async def test_unreachable_docs_never_report_up_to_date(self):
        watch._cached = None
        watch._next_check = 0
        with patch.object(watch, 'BASELINE') as path, patch.object(watch, 'fetch_documents', AsyncMock(side_effect=OSError)):
            path.read_text.return_value = '{"documents": {"/api/docs/changelog": "old"}}'
            result = await watch.get_release_status()
        self.assertEqual(result['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
