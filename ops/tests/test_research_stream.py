"""Installed SDK wire proof with real sockets, processes and private state denied."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
from research_worker import OFFLINE_PYTHON  # noqa: E402

SDK_PROBE = r'''
import importlib.util, json, os, pathlib, sys, threading
sys.dont_write_bytecode = True
root = pathlib.Path('/Users/nav/.hermes')
permitted = (pathlib.Path(sys.prefix).resolve(), pathlib.Path(sys.base_prefix).resolve())
events = []
def audit(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.spawn', 'socket.connect', 'socket.getaddrinfo'):
        events.append(event)
        raise RuntimeError('offline_effect_denied')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = pathlib.Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(root) and not any(path.is_relative_to(entry) for entry in permitted):
            events.append('private_or_bootstrap_access')
            raise RuntimeError('offline_private_state_denied')
sys.addaudithook(audit)
import httpx, openai
spec = importlib.util.spec_from_file_location('native', sys.argv[1])
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
messages = [{'role': 'system', 'content': 'fixture only'}, {'role': 'user', 'content': 'copy fixture'}]
guard = native.WireGuard('offline-key', messages)
guard.phase = 'run'
produced = []
abort_marker = object()
class Wire(httpx.SyncByteStream):
    def __iter__(self):
        for index, delta, reason in ((1, {'content': 'copied'}, None), (2, {}, 'stop')):
            produced.append(index)
            yield ('data: ' + json.dumps({'id': 'fixture', 'object': 'chat.completion.chunk', 'created': 1,
                'model': native.MODEL, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}) + '\n\n').encode()
        produced.append(3)
        yield b'data: [DONE]\n\n'
def handle(request):
    guard.admit(str(request.url), request.method, request.content)
    return native.bounded_stream_response(httpx, httpx.Response(200, request=request,
        headers={'content-type': 'text/event-stream'}, stream=Wire(),
        extensions={'network_stream': abort_marker}), guard, threading.local())
with openai.OpenAI(api_key='offline-key', base_url=native.ENDPOINT.rsplit('/', 2)[0], max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
    # Freeze fixture-only OS header metadata; SDK discovery otherwise invokes sw_vers.
    client._platform = 'Unknown'
    stream = client.chat.completions.create(model=native.MODEL, messages=messages, max_tokens=1024,
        stream=True, stream_options={'include_usage': True})
    assert stream.response.extensions['network_stream'] is abort_marker
    first = next(stream)
    assert first.choices[0].delta.content == 'copied'
    assert produced == [1], produced
    list(stream)
assert guard.requests == 1 and guard.blocked == 0
assert guard.stream_done and guard.finish_reason == 'stop'
assert not events, events
assert 'hermes_bootstrap' not in sys.modules
print(json.dumps({'sdk_version': openai.__version__, 'http_request_count': guard.requests,
    'blocked_http_attempt_count': guard.blocked, 'incremental_before_completion': True,
    'wire_body_bytes': guard.request_body_bytes, 'output_cap': guard.output_cap,
    'stream_done': guard.stream_done, 'finish_reason': guard.finish_reason,
    'effect_attempts': events, 'bootstrap_loaded': False, **guard.diagnostics()}, sort_keys=True))
'''


class InstalledSDKStreamTests(unittest.TestCase):
    def test_preinstalled_sdk_consumes_first_delta_before_later_bytes_without_effects(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('HERMES_')
               and not any(word in key.upper() for word in
                   ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION'))}
        with tempfile.TemporaryDirectory(prefix='research-sdk-offline-') as home:
            env.update(HOME=home, PYTHONDONTWRITEBYTECODE='1', DO_NOT_TRACK='1')
            result = subprocess.run([str(OFFLINE_PYTHON), '-I', '-c', SDK_PROBE,
                str(OPS / 'research_native_role.py')], env=env, cwd=home, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode()[:1500])
        proof = json.loads(result.stdout)
        self.assertTrue(proof['incremental_before_completion'])
        self.assertEqual(proof['effect_attempts'], [])
        self.assertFalse(proof['bootstrap_loaded'])
        self.assertTrue(proof['stream_done'])
        self.assertEqual(proof['http_request_count'], 1)
        self.assertEqual(proof['blocked_http_attempt_count'], 0)
        self.assertEqual(proof['output_cap'], 1024)


if __name__ == '__main__':
    unittest.main()
