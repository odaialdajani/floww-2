"""Preinstalled SDK + exact registered prompts + SSE guard, with effects denied."""
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

PROBE = r'''
import importlib.util, json, os, pathlib, sys, threading
events = []
def effects(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system', 'os.exec', 'os.spawn'):
        events.append(event)
        raise RuntimeError('offline_effect_refused')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = pathlib.Path(os.fsdecode(args[0])).resolve()
        if path.name == '.env' or path.name.startswith('hermes_bootstrap.'):
            events.append('private_or_bootstrap_access')
            raise RuntimeError('offline_private_access_refused')
        if path.is_relative_to(pathlib.Path('/Users/nav/.hermes')):
            if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                events.append('production_write')
                raise RuntimeError('offline_write_refused')
            if 'profiles' in path.parts or path.name in ('config.yaml', 'active_profile'):
                events.append('production_profile_access')
                raise RuntimeError('offline_profile_refused')
sys.addaudithook(effects)
import httpx, openai
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
native = module('native', sys.argv[1])
task = module('heatmap', sys.argv[2])
investigator = None
proof = []
for role in ('research', 'audit'):
    packet = task.request_for(role, investigator if role == 'audit' else None)
    messages = [{'role': 'system', 'content': native.system_for(packet)},
                {'role': 'user', 'content': native.prompt_for(packet, role)}]
    guard = native.WireGuard('offline-key', messages)
    guard.phase = 'run'
    response = task.fixture_response(packet, role)
    output = task.canonical(response)
    produced = []
    class Wire(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(0, len(output), 37):
                produced.append(index)
                event = {'id': 'offline', 'object': 'chat.completion.chunk', 'created': 1,
                    'model': native.MODEL, 'choices': [{'index': 0,
                    'delta': {'content': output[index:index + 37]}, 'finish_reason': None}]}
                yield ('data: ' + json.dumps(event) + '\n\n').encode()
            yield ('data: ' + json.dumps({'id': 'offline', 'object': 'chat.completion.chunk', 'created': 1,
                'model': native.MODEL, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n').encode()
            yield b'data: [DONE]\n\n'
    def handle(request):
        guard.admit(str(request.url), request.method, request.content)
        return native.bounded_stream_response(httpx, httpx.Response(200, request=request,
            headers={'content-type': 'text/event-stream'}, stream=Wire()), guard, threading.local())
    with openai.OpenAI(api_key='offline-key', base_url=native.ENDPOINT.rsplit('/', 2)[0], max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        client._platform = 'Unknown'
        stream = client.chat.completions.create(model=native.MODEL, messages=messages,
            max_tokens=1024, stream=True, stream_options={'include_usage': True})
        first = next(stream)
        assert len(produced) == 1, produced
        text = first.choices[0].delta.content or ''
        for chunk in stream:
            text += chunk.choices[0].delta.content or '' if chunk.choices else ''
    decoded = task.parse_response(text)
    validation = (task.validate_investigator(decoded) if role == 'research'
                  else task.validate_audit(investigator, decoded))
    assert validation['accepted'], validation
    if role == 'research':
        investigator = decoded
    assert guard.requests == 1 and guard.blocked == 0 and guard.stream_done
    proof.append({'role': role, 'http_request_count': guard.requests,
        'blocked_http_attempt_count': guard.blocked, 'output_cap': guard.output_cap,
        'wire_body_bytes': guard.request_body_bytes, 'stream_done': guard.stream_done,
        'finish_reason': guard.finish_reason, 'incremental_before_completion': True,
        'validated_closed_output': validation['accepted'], 'executable': False})
assert not events, events
assert 'hermes_bootstrap' not in sys.modules
print(json.dumps({'installed_sdk': openai.__version__, 'roles': proof,
    'effect_attempts': events, 'bootstrap_loaded': False,
    'proof_scope': 'installed_sdk_mock_wire_only_not_native_completion'}, sort_keys=True))
'''


class InstalledHeatmapSDKTests(unittest.TestCase):
    def test_exact_registered_investigator_then_audit_prompts_cross_sdk_guard_without_effects(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('HERMES_')
               and not any(word in key.upper() for word in
                           ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION'))}
        with tempfile.TemporaryDirectory(prefix='heatmap-sdk-offline-') as home:
            env.update(HOME=home, PYTHONDONTWRITEBYTECODE='1', DO_NOT_TRACK='1')
            result = subprocess.run([str(OFFLINE_PYTHON), '-I', '-c', PROBE,
                                     str(OPS / 'research_native_role.py'), str(OPS / 'heatmap_research.py')],
                                    env=env, cwd=home, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode()[:1500])
        proof = json.loads(result.stdout)
        self.assertEqual(proof['effect_attempts'], [])
        self.assertFalse(proof['bootstrap_loaded'])
        self.assertEqual([role['role'] for role in proof['roles']], ['research', 'audit'])
        self.assertTrue(all(role['http_request_count'] == 1 and role['blocked_http_attempt_count'] == 0
                            and role['output_cap'] == 1024 and role['stream_done']
                            and role['validated_closed_output'] for role in proof['roles']))
        print(json.dumps(proof, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
