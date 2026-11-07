"""Behavior tests use only temporary files and mocked local transports."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'watchdog.py'


class CommandContractTests(unittest.TestCase):
    def test_missing_sample_is_unknown_and_nonzero_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPT), '--state-dir', directory,
                                     'status'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('"state": "unknown"', result.stdout)
        self.assertEqual(json.loads(result.stdout)['freshness'], 'unknown')

# Imports below the CLI-only contract let the initial red test run before
# the implementation exists. They remain ordinary stdlib unit tests.
import hashlib
import http.server
import threading
import multiprocessing
import os
import stat
import time
from unittest import mock

sys.path.insert(0, str(SCRIPT.parent))
import watchdog

SHA = 'a' * 40
HTML = b'<!doctype html><title>FLOWW</title>'


def fixture_pin(directory, sha=SHA):
    root = pathlib.Path(directory) / 'runtime'
    release = root / 'releases' / sha[:9]
    index = release / 'frontend' / 'build' / 'index.html'
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(HTML)
    (root / 'runtime.json').write_text(json.dumps({'release': str(release), 'sha': sha,
                                                  'store': '/must/not/read/active.duckdb'}))
    return root


def good_probe(name, state_dir):
    if name == 'backend_version':
        return {'state': 'ok', 'sha': 'aaaaaaaaa', 'http_status': 200}
    if name == 'backend_health':
        return {'state': 'ok', 'health': 'ok', 'http_status': 200}
    if name == 'frontend':
        return {'state': 'ok', 'sha256': hashlib.sha256(HTML).hexdigest(), 'http_status': 200}
    raise AssertionError('Unexpected endpoint')


def hold_lease(directory, ready, release):
    with watchdog.Lease(pathlib.Path(directory)):
        ready.set()
        release.wait(5)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.runtime = fixture_pin(self.directory)
        self.state = self.directory / 'operations'

    def check(self, probe=good_probe, clock=lambda: 1000):
        return watchdog.check_once(self.state, runtime_root=self.runtime,
                                   probe=probe, clock=clock)

    def test_matching_pin_and_both_services_publish_a_private_healthy_receipt(self):
        result = self.check()
        self.assertEqual(result['state'], 'healthy')
        self.assertEqual(result['identity']['state'], 'matched')
        self.assertEqual(result['identity']['backend_sha'], 'aaaaaaaaa')
        self.assertFalse(result['capabilities']['execution'])
        self.assertFalse(result['capabilities']['liquid'])
        self.assertEqual(watchdog.exit_code(result), 0)
        stored = json.loads((self.state / 'status.json').read_text())
        self.assertEqual(stored['state'], 'healthy')
        self.assertEqual(len(list((self.state / 'snapshots').glob('*.json'))), 1)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.state / 'status.json').stat().st_mode), 0o600)

    def test_missing_pin_is_unknown_even_when_all_http_responses_are_good(self):
        (self.runtime / 'runtime.json').unlink()
        result = self.check()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['identity']['state'], 'unknown')
        self.assertEqual(watchdog.exit_code(result), 2)

    def test_pin_cannot_escape_the_release_directory(self):
        outside = self.directory / 'outside'
        outside.mkdir()
        (self.runtime / 'runtime.json').write_text(json.dumps({'sha': SHA, 'release': str(outside)}))
        self.assertEqual(watchdog.load_pin(self.runtime)['state'], 'unknown')

    def test_backend_revision_mismatch_is_unhealthy(self):
        def changed(name, directory):
            result = good_probe(name, directory)
            if name == 'backend_version':
                result['sha'] = 'bbbbbbbbb'
            return result
        result = self.check(changed)
        self.assertEqual(result['state'], 'unhealthy')
        self.assertEqual(result['identity']['state'], 'mismatch')

    def test_frontend_html_mismatch_is_unhealthy(self):
        def changed(name, directory):
            result = good_probe(name, directory)
            if name == 'frontend':
                result['sha256'] = '0' * 64
            return result
        result = self.check(changed)
        self.assertEqual(result['state'], 'unhealthy')
        self.assertEqual(result['identity']['state'], 'mismatch')

    def test_unknown_response_and_failed_transport_remain_distinct(self):
        for state, overall in [('unknown', 'unknown'), ('failed', 'unhealthy')]:
            with self.subTest(state=state):
                def changed(name, directory):
                    return {'state': state, 'reason': 'fixture'} if name == 'backend_health' else good_probe(name, directory)
                result = self.check(changed)
                self.assertEqual(result['state'], overall)
                self.assertEqual(result['checks']['backend_health']['state'], state)

    def test_pause_sentinel_prevents_all_new_network_reads(self):
        watchdog.pause(self.state, clock=lambda: 1000)
        def forbidden(*args):
            raise AssertionError('A paused observer attempted a network read')
        result = self.check(forbidden)
        self.assertEqual(result['state'], 'paused')
        self.assertEqual(result['checks'], {})
        self.assertNotEqual(watchdog.exit_code(result), 0)

    def test_pause_between_probes_suppresses_the_remaining_reads(self):
        seen = []
        def pausing(name, directory):
            if seen:
                raise AssertionError('A new read was started after pause')
            seen.append(name)
            watchdog.pause(self.state, clock=lambda: 1000)
            return good_probe(name, directory)
        result = self.check(pausing)
        self.assertEqual(result['state'], 'paused')
        self.assertEqual(set(result['checks']), {'backend_version'})

    def test_resume_only_clears_pause_and_does_not_claim_a_fresh_sample(self):
        self.check()
        watchdog.pause(self.state, clock=lambda: 1000)
        with mock.patch.object(watchdog, 'run_probe', side_effect=AssertionError('resume read network')):
            result = watchdog.resume(self.state, clock=lambda: 1601)
        self.assertFalse((self.state / 'STOP').exists())
        self.assertEqual(result['freshness'], 'stale')
        self.assertEqual(result['sample_age_seconds'], 601)

    def test_fifo_metadata_is_rejected_before_a_blocking_read(self):
        watchdog.ensure_private_dir(self.state)
        code = ("import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
                "import watchdog;"
                "p=Path(sys.argv[2]);"
                "print(json.dumps(watchdog.load_pin(p) if sys.argv[3]=='pin' else watchdog.status(p)))")
        for kind in ['pin', 'status']:
            with self.subTest(kind=kind):
                target = self.runtime / 'runtime.json' if kind == 'pin' else self.state / 'status.json'
                if target.exists():
                    target.unlink()
                os.mkfifo(str(target), 0o600)
                try:
                    result = subprocess.run([sys.executable, '-I', '-c', code, str(SCRIPT.parent),
                                             str(self.runtime if kind == 'pin' else self.state), kind],
                                            capture_output=True, text=True, timeout=0.5)
                except subprocess.TimeoutExpired:
                    self.fail('FIFO metadata blocked before regular-file validation')
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)['state'], 'unknown')

    def test_fifo_staging_file_is_rejected_before_a_blocking_write(self):
        watchdog.ensure_private_dir(self.state)
        os.mkfifo(str(self.state / '.STOP.pending'), 0o600)
        try:
            result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--state-dir', str(self.state),
                                     'pause'], capture_output=True, text=True, timeout=0.5)
        except subprocess.TimeoutExpired:
            self.fail('FIFO staging blocked before regular-file validation')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['state'], 'unknown')
        self.assertFalse((self.state / 'STOP').exists())

    def test_resume_after_a_paused_sample_waits_for_a_new_check(self):
        watchdog.pause(self.state, clock=lambda: 1000)
        self.check()
        result = watchdog.resume(self.state, clock=lambda: 1001)
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['desired_state'], 'running')
        self.assertEqual(result['reason'], 'check_needed_after_resume')
        self.assertNotEqual(watchdog.exit_code(result), 0)

    def test_a_second_process_cannot_collect_or_overwrite_the_lease_owner(self):
        watchdog.ensure_private_dir(self.state)
        context = multiprocessing.get_context('fork')
        ready, release = context.Event(), context.Event()
        child = context.Process(target=hold_lease, args=(str(self.state), ready, release))
        child.start()
        try:
            self.assertTrue(ready.wait(3))
            def forbidden(*args):
                raise AssertionError('A competing process performed a read')
            result = self.check(forbidden)
            self.assertEqual(result['state'], 'busy')
            self.assertFalse((self.state / 'status.json').exists())
        finally:
            release.set()
            child.join(3)
            if child.is_alive():
                child.terminate()
                child.join()
        self.assertEqual(child.exitcode, 0)

    def test_status_reports_stale_and_future_dated_samples_without_network(self):
        self.check()
        old = watchdog.status(self.state, clock=lambda: 1601)
        self.assertEqual(old['freshness'], 'stale')
        self.assertEqual(watchdog.exit_code(old), 5)
        future = watchdog.status(self.state, clock=lambda: 999)
        self.assertEqual(future['freshness'], 'unknown')
        self.assertEqual(watchdog.exit_code(future), 2)

    def test_snapshot_retention_and_event_rotation_are_bounded(self):
        with mock.patch.object(watchdog, 'MAX_SNAPSHOTS', 3), mock.patch.object(watchdog, 'EVENT_BYTES', 256):
            for number in range(12):
                self.check(clock=lambda n=number: 1000 + n)
        snapshots = sorted((self.state / 'snapshots').glob('*.json'))
        self.assertEqual(len(snapshots), 3)
        self.assertTrue((self.state / 'events.1.jsonl').exists())
        for path in [self.state / 'events.jsonl', self.state / 'events.1.jsonl']:
            self.assertLessEqual(path.stat().st_size, 256)
            for line in path.read_text().splitlines():
                json.loads(line)
        self.assertEqual(watchdog.status(self.state, clock=lambda: 1011)['state'], 'healthy')

    def test_symlink_state_directory_is_refused_without_changing_its_target(self):
        outside = self.directory / 'personal'
        outside.mkdir(mode=0o755)
        original_mode = stat.S_IMODE(outside.stat().st_mode)
        self.state.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.check()
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode), original_mode)
        self.assertEqual(list(outside.iterdir()), [])

    def test_release_pin_changed_during_probe_is_unknown_not_current_acceptance(self):
        def changing(name, directory):
            result = good_probe(name, directory)
            if name == 'frontend':
                fixture_pin(self.directory, 'b' * 40)
            return result
        result = self.check(changing)
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['identity']['reason'], 'pin_changed_during_check')


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = pathlib.Path(self.temporary.name)

    def response(self, body=b'{}', status_code=200, headers=None):
        response = mock.Mock()
        response.status = status_code
        response.getheader.side_effect = lambda key, default=None: (headers or {}).get(key, default)
        response.read.return_value = body
        return response

    def test_transport_uses_only_the_fixed_numeric_loopback_gets(self):
        cases = [('backend_version', 8213, '/api/version', b'{"sha":"aaaaaaaaa"}'),
                 ('backend_health', 8213, '/health', b'{"status":"ok"}'),
                 ('frontend', 3000, '/', HTML)]
        for name, port, path, body in cases:
            with self.subTest(name=name):
                connection = mock.Mock()
                connection.getresponse.return_value = self.response(body)
                with mock.patch.object(watchdog.http.client, 'HTTPConnection', return_value=connection) as factory:
                    result = watchdog.probe_endpoint(name, self.state)
                self.assertEqual(result['state'], 'ok')
                factory.assert_called_once_with('127.0.0.1', port, timeout=2.0)
                args = connection.request.call_args.args
                self.assertEqual(args, ('GET', path))
                self.assertEqual(connection.request.call_args.kwargs['headers']['Accept-Encoding'], 'identity')

    def test_redirect_is_reported_and_never_followed_or_read(self):
        connection = mock.Mock()
        response = self.response(status_code=302, headers={'Location': 'https://example.invalid/account'})
        response.read.side_effect = AssertionError('Redirect response was read')
        connection.getresponse.return_value = response
        with mock.patch.object(watchdog.http.client, 'HTTPConnection', return_value=connection) as factory:
            result = watchdog.probe_endpoint('frontend', self.state)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['reason'], 'redirect_blocked')
        self.assertEqual(factory.call_count, 1)

    def test_response_larger_than_body_cap_is_unknown_without_persisting_the_body(self):
        connection = mock.Mock()
        connection.getresponse.return_value = self.response(b'x' * (256 * 1024 + 1))
        with mock.patch.object(watchdog.http.client, 'HTTPConnection', return_value=connection):
            result = watchdog.probe_endpoint('frontend', self.state)
        self.assertEqual(result, {'state': 'unknown', 'reason': 'response_too_large', 'http_status': 200})
        connection.getresponse.return_value.read.assert_called_once_with(256 * 1024 + 1)

    def test_truncated_declared_body_is_unknown_with_a_real_local_http_server(self):
        class ShortBody(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '100')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(('127.0.0.1', 0), ShortBody)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            with mock.patch.dict(watchdog.ENDPOINTS, {'backend_health': (server.server_port, '/health')}):
                result = watchdog.probe_endpoint('backend_health', self.state)
            self.assertEqual(result['state'], 'unknown')
            self.assertEqual(result['reason'], 'truncated_response')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_malformed_json_and_revision_and_compressed_body_are_unknown(self):
        cases = [('backend_health', b'not json', {}),
                 ('backend_version', b'{"sha":"main"}', {}),
                 ('frontend', b'compressed', {'Content-Encoding': 'gzip'})]
        for name, body, headers in cases:
            with self.subTest(name=name):
                connection = mock.Mock()
                connection.getresponse.return_value = self.response(body, headers=headers)
                with mock.patch.object(watchdog.http.client, 'HTTPConnection', return_value=connection):
                    self.assertEqual(watchdog.probe_endpoint(name, self.state)['state'], 'unknown')

    def test_paused_child_does_not_open_a_socket(self):
        (self.state / 'STOP').write_text('paused')
        with mock.patch.object(watchdog.http.client, 'HTTPConnection', side_effect=AssertionError('socket opened')):
            self.assertEqual(watchdog.probe_endpoint('frontend', self.state)['state'], 'paused')

    def test_deadline_kills_and_reaps_a_slow_probe_process(self):
        original_popen = subprocess.Popen
        children = []
        def local_slow_child(args, **kwargs):
            child = original_popen([sys.executable, '-c', 'import time; time.sleep(5)'], **kwargs)
            children.append(child)
            return child
        started = time.monotonic()
        with mock.patch.object(watchdog.subprocess, 'Popen', side_effect=local_slow_child), \
             mock.patch.object(watchdog, 'PROBE_TIMEOUT', 0.1):
            result = watchdog.run_probe('frontend', self.state)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['reason'], 'deadline_exceeded')
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIsNotNone(children[0].poll())

    def test_arbitrary_endpoint_name_is_refused_before_opening_a_socket(self):
        with mock.patch.object(watchdog.http.client, 'HTTPConnection', side_effect=AssertionError('socket opened')):
            with self.assertRaises(ValueError):
                watchdog.probe_endpoint('https://example.invalid', self.state)


if __name__ == '__main__':
    unittest.main()
