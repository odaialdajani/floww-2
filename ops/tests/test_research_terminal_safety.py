"""Fail-closed terminal state and independently guarded native offline modes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
import research_native_role as native  # noqa: E402
import research_worker as worker  # noqa: E402


def wire(choice=None, **extra):
    event = {'choices': [] if choice is None else [choice], **extra}
    return ('data: ' + json.dumps(event) + '\n\n').encode()


def choice(reason=None, content=None, index=0, **extra):
    delta = {} if content is None else {'content': content}
    return {'index': index, 'delta': delta, 'finish_reason': reason, **extra}


class TerminalSafetyTests(unittest.TestCase):
    def guard(self):
        return native.WireGuard('fixture-only', [])

    def test_forbidden_finish_can_never_be_overwritten_by_stop(self):
        for reason in ('length', 'content_filter', 'tool_calls', 'unknown'):
            with self.subTest(reason=reason):
                guard = self.guard()
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(wire(choice(reason)))
                first_refusal = guard.stream_refusal
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(wire(choice('stop')) + b'data: [DONE]\n\n')
                self.assertEqual(guard.finish_reason, reason)
                self.assertEqual(guard.stream_refusal, first_refusal)
                self.assertFalse(guard.stream_done)

    def test_repeat_terminal_and_content_after_stop_are_permanent_refusals(self):
        for later in (choice('stop'), choice('length'), choice(content='later'), choice()):
            with self.subTest(later=later):
                guard = self.guard()
                guard.observe_stream_bytes(wire(choice('stop')))
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(wire(later))
                refusal = guard.stream_refusal
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(b'data: [DONE]\n\n')
                self.assertEqual(guard.stream_refusal, refusal)
                self.assertFalse(guard.stream_done)

    def test_only_the_single_admitted_choice_zero_is_allowed(self):
        for choices in ([choice(index=1)], [choice(), choice('stop')],
                        [{'delta': {}, 'finish_reason': 'stop'}],
                        [choice(index=True)]):
            with self.subTest(choices=choices):
                guard = self.guard()
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(wire(choices=choices))
                self.assertFalse(guard.stream_done)

    def test_done_requires_a_valid_stop_even_when_sdk_does_not_read_eof(self):
        guard = self.guard()
        guard.observe_stream_bytes(wire(choice(content='valid JSON can still be incomplete')))
        with self.assertRaises(native.NativeError):
            guard.observe_stream_bytes(b'data: [DONE]\n\n')
        self.assertFalse(guard.stream_done)

    def test_stop_then_separate_usage_and_fragmented_done_remains_valid(self):
        guard = self.guard()
        payload = (wire(choice(content='copied')) + wire(choice('stop'))
                   + wire(usage={'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5})
                   + b'data: [DONE]\r\n\r\n')
        for index in range(0, len(payload), 5):
            guard.observe_stream_bytes(payload[index:index + 5])
        guard.finish_stream()
        self.assertTrue(guard.stream_done)
        self.assertIsNone(guard.stream_refusal)
        self.assertEqual(guard.response_usage['total_tokens'], 5)

    def test_received_trailing_partial_event_after_done_is_rejected_before_sdk_return(self):
        guard = self.guard()
        with self.assertRaises(native.NativeError):
            guard.observe_stream_bytes(wire(choice('stop')) + b'data: [DONE]\n\ndata: {')
        self.assertEqual(guard.stream_refusal, 'native_stream_data_after_done')

    def test_eof_refusal_cannot_be_repaired_by_later_terminal_bytes(self):
        guard = self.guard()
        guard.observe_stream_bytes(wire(choice(content='partial')))
        with self.assertRaises(native.NativeError):
            guard.finish_stream()
        with self.assertRaises(native.NativeError):
            guard.observe_stream_bytes(wire(choice('stop')) + b'data: [DONE]\n\n')
        self.assertEqual(guard.stream_refusal, 'native_stream_incomplete')
        self.assertFalse(guard.stream_done)

    def test_refusal_or_tool_delta_cannot_be_accepted_by_later_stop(self):
        for delta in ({'refusal': 'no'}, {'tool_calls': [{'index': 0}]},
                      {'function_call': {'name': 'forbidden'}}):
            with self.subTest(delta=delta):
                guard = self.guard()
                with self.assertRaises(native.NativeError):
                    guard.observe_stream_bytes(wire({'index': 0, 'delta': delta, 'finish_reason': None}))
                self.assertIsNotNone(guard.stream_refusal)


OFFLINE_GUARD = r'''
import json, os, runpy, sys, traceback
from pathlib import Path
sys.dont_write_bytecode = True
root = Path('/Users/nav/.hermes')
allowed = (root / 'hermes-agent', Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
events = []
def audit(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.spawn', 'socket.connect', 'socket.getaddrinfo'):
        events.append({'event': event, 'frames': [(frame.filename, frame.name, frame.lineno)
            for frame in traceback.extract_stack(limit=24)]})
        raise RuntimeError('outer_denied_effect')
    if event in ('open', 'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.chmod'):
        for value in args[:2] if event == 'os.rename' else args[:1]:
            if not isinstance(value, (str, bytes, os.PathLike)):
                continue
            path = Path(os.fsdecode(value)).resolve()
            if path.name.startswith('hermes_bootstrap.') and path.is_relative_to(root / 'hermes-agent'):
                events.append('bootstrap_source_access')
                raise RuntimeError('outer_denied_bootstrap')
            if path.is_relative_to(Path('/Users/nav/Library')):
                events.append('protected_library_access')
                raise RuntimeError('outer_denied_library')
            if path.is_relative_to(root):
                writing = event != 'open' or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
                if writing or not any(path.is_relative_to(entry) for entry in allowed):
                    events.append('production_private_access')
                    raise RuntimeError('outer_denied_private')
sys.addaudithook(audit)
sys.argv = [sys.argv[1], '--self-test' if sys.argv[2] == 'selftest' else '--offline-replay']
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
except SystemExit as exc:
    status = exc.code
except BaseException as exc:
    status = type(exc).__name__
os.write(1, (json.dumps({'guard_events': events, 'exit_status': status,
    'bootstrap_source_loaded': getattr(sys.modules.get('hermes_bootstrap'), '__file__', None) is not None,
    'native_agent_loaded': 'run_agent' in sys.modules}) + '\n').encode())
'''


class GuardedOfflineModeTests(unittest.TestCase):
    def run_mode(self, mode, fault=None):
        # Public synthetic fixture, never copied from production profile/config.
        sys.path.insert(0, str(OPS / 'tests'))
        import research_intake as intake
        from test_research_worker import fixture
        packet = intake.compile_snapshot(fixture(), 1794085822)
        env = {k: v for k, v in os.environ.items() if not k.startswith('HERMES_')
               and not any(s in k.upper() for s in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION'))}
        with tempfile.TemporaryDirectory(prefix='offline-replay-', dir='/Users/nav') as folder:
            scratch = Path(folder)
            profile = scratch / 'offline-profile'
            profile.mkdir(mode=0o700)
            # These fixed settings match the admitted tool-free role envelope.
            profile.joinpath('config.yaml').write_text(json.dumps({
                'model': {'provider': 'nvidia', 'default': native.MODEL,
                          'base_url': native.ENDPOINT.rsplit('/', 2)[0], 'api_mode': 'chat_completions'},
                'agent': {'max_turns': 20, 'api_max_retries': 0, 'auto_recovery_cycles': 0,
                          'disabled_toolsets': ['all'], 'verify_on_stop': False,
                          'environment_probe': False, 'coding_context': 'off'},
                'memory': {'memory_enabled': False, 'user_profile_enabled': False},
                'kanban': {'dispatch_in_gateway': False},
                'auxiliary': {name: {'model': native.MODEL, 'provider': 'nvidia'} for name in (
                    'vision', 'compression', 'approval', 'review', 'mcp', 'title_generation',
                    'memory_query_rewrite', 'tts_audio_tags', 'voice_chat', 'triage_specifier',
                    'kanban_decomposer', 'profile_describer', 'goal_judge', 'group_router',
                    'curator', 'monitor', 'background_review', 'moa_reference', 'moa_aggregator')},
                'toolsets': [], 'tool_search': {'enabled': False}}))
            profile.joinpath('ESTOP').write_text('fixture-held')
            scratch.joinpath('home').mkdir(mode=0o700)
            wrapper = scratch / 'outer_guard.py'
            wrapper.write_text(OFFLINE_GUARD)
            env.update(HERMES_HOME=str(profile), HOME=str(scratch / 'home'), HERMES_IGNORE_RULES='1',
                       PYTHONDONTWRITEBYTECODE='1', DO_NOT_TRACK='1')
            supplied = {'role': 'research', 'packet': packet}
            if fault:
                supplied['offline_fault'] = fault
            payload = (json.dumps(supplied) + '\n').encode()
            if mode != 'preflight':
                # The isolated marker simulates parent admission, never real ESTOP.
                # Wait for ready before unpausing using a small protocol driver.
                supplied_run = 'RUN' if mode != 'selftest' else ''
            else:
                supplied_run = ''
            process = subprocess.Popen([str(worker.OFFLINE_PYTHON), '-I', str(wrapper),
                str(OPS / 'research_native_role.py'), mode], env=env, cwd=scratch,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if mode == 'selftest':
                stdout, stderr = process.communicate(timeout=20)
            else:
                process.stdin.write(payload)
                process.stdin.flush()
                first = process.stdout.readline()
                if supplied_run and first and json.loads(first).get('phase') == 'ready':
                    profile.joinpath('ESTOP').unlink()
                    process.stdin.write(b'RUN\n')
                    process.stdin.flush()
                remainder, stderr = process.communicate(timeout=20)
                stdout = first + remainder
            self.assertEqual(process.returncode, 0, stderr.decode()[:1000])
            return [json.loads(line) for line in stdout.splitlines()]

    def test_ordinary_replay_and_preflight_never_load_bootstrap_or_attempt_effects(self):
        for mode in ('preflight', 'replay'):
            with self.subTest(mode=mode):
                lines = self.run_mode(mode)
                self.assertEqual(lines[-1]['guard_events'], [], lines)
                self.assertFalse(lines[-1]['bootstrap_source_loaded'])
                self.assertTrue(lines[-1]['native_agent_loaded'], lines)
                if mode == 'replay':
                    self.assertTrue(lines[-2]['success'], lines)
                    self.assertEqual(lines[-2]['http_request_count'], 1)
                else:
                    self.assertEqual(lines[-2]['http_request_count'], 0)

    def test_fault_modes_never_load_bootstrap_or_make_more_than_one_fake_post(self):
        for fault in ('partial_timeout', 'missing_done', 'length', 'pending', 'response_limit'):
            with self.subTest(fault=fault):
                lines = self.run_mode('replay', fault)
                self.assertEqual(lines[-1]['guard_events'], [], lines)
                self.assertFalse(lines[-1]['bootstrap_source_loaded'])
                self.assertFalse(lines[-2]['success'], lines)
                self.assertEqual(lines[-2]['http_request_count'], 1, lines)

    def test_native_sdk_cannot_accept_conflicting_terminal_fixture(self):
        for fault in ('length_then_stop', 'filter_then_stop', 'duplicate_stop', 'content_after_stop',
                      'choice_conflict', 'refusal_then_stop'):
            with self.subTest(fault=fault):
                lines = self.run_mode('replay', fault)
                self.assertEqual(lines[-1]['guard_events'], [], lines)
                self.assertFalse(lines[-1]['bootstrap_source_loaded'])
                result = lines[-2]
                self.assertFalse(result['success'], lines)
                self.assertFalse(result['stream_done'])
                self.assertIsNotNone(result['stream_refusal'])
                self.assertEqual(result['http_request_count'], 1, lines)


if __name__ == '__main__':
    unittest.main()
