#!/usr/bin/env python3
"""Single native Hermes role, run only through research_worker parent lease.

The native agent receives a placeholder credential. Only this adapter's HTTP
boundary holds the scoped key and adds Authorization to the single admitted POST.
No installed Hermes files are changed. Pricing discovery is disabled in-process;
cost remains unknown. These controls constrain this native path, not arbitrary OS
code. The model has no executable tools and cannot choose a path or destination.
"""
import contextlib
import hashlib
import json
import os
import signal
import socket
import sys
import threading
import time
import traceback
import types
from pathlib import Path

MODEL = 'minimaxai/minimax-m3.1-flash'
ENDPOINT = 'https://integrate.api.nvidia.com/v1/chat/completions'
NATIVE_SOURCE = Path('/Users/nav/.hermes/hermes-agent')
SYSTEM = ('You copy literal historical facts from one sanitized saved-observation packet. '
          'You have no tools, personal history, memory, account or execution authority. '
          'Return only the requested closed JSON object. Stale facts remain stale. '
          'Never add advice, prose, confidence, a signal or an action.')
MAX_INPUT = 64 * 1024
MAX_REPLY = 128 * 1024


class NativeError(ValueError):
    """Stable nonsecret wire refusal."""


class WireGuard:
    def __init__(self, key, expected_messages):
        self.key = key
        self.expected_messages = expected_messages
        self.requests = 0
        self.blocked = 0
        self.phase = 'preflight'
        self.output_cap = None
        self.refusals = []
        self.transport_error_type = None
        self.http_status = None
        self.finish_reason = None
        self.response_usage = {}
        self.blocked_origins = []

    def admit(self, url, method, content):
        try:
            if self.phase != 'run' or self.requests:
                raise NativeError('additional_or_premature_http')
            if url != ENDPOINT or method != 'POST':
                raise NativeError('endpoint_not_allowed')
            if len(content) > MAX_INPUT or self.key.encode() in content:
                raise NativeError('unsafe_request_body')
            body = json.loads(content)
            caps = [body[k] for k in ('max_tokens', 'max_completion_tokens', 'max_output_tokens') if k in body]
            if not caps or any(type(cap) is not int or not 0 < cap <= 1024 for cap in caps):
                raise NativeError('output_cap_refused')
            if body.get('model') != MODEL or body.get('tools') or body.get('functions') or body.get('stream'):
                raise NativeError('request_envelope_refused')
            if body.get('messages') != self.expected_messages:
                raise NativeError('untrusted_message_context')
            self.requests += 1
            self.output_cap = min(caps)
        except (NativeError, ValueError, TypeError, KeyError) as exc:
            self.blocked += 1
            self.refusals.append(str(exc) if isinstance(exc, NativeError) else 'invalid_wire_json')
            if len(self.blocked_origins) < 8:
                self.blocked_origins.append([{'module': str(Path(frame.filename).relative_to(NATIVE_SOURCE)),
                    'function': frame.name, 'line': frame.lineno} for frame in traceback.extract_stack(limit=24)
                    if frame.filename.startswith(str(NATIVE_SOURCE) + '/')][-8:])
            raise NativeError('wire_policy_refused') from None


def rejection_fixture():
    from agent.agent_runtime_helpers import repair_tool_call
    from agent.turn_tool_round import run_tool_round
    from hermes_cli.observability import shared_metrics_model
    shared_metrics_model.record_tool_call_quality = lambda *a, **k: None
    names = ['terminal', 'write_file', 'delegate_task', 'kanban_attach_url', 'memory', 'web_search']
    cases = []
    executor_calls = 0
    def forbidden(*a, **k):
        nonlocal executor_calls
        executor_calls += 1
        raise NativeError('fixture_reached_executor_or_persistence')
    for calls in [[name] for name in names] + [names]:
        agent = types.SimpleNamespace(valid_tool_names=set(), quiet_mode=True, verbose_logging=False,
            log_prefix='', _invalid_tool_retries=0, _uniquify_tool_call_ids=lambda *a, **k: None,
            _buffer_vprint=lambda *a, **k: None, _vprint=lambda *a, **k: None,
            _execute_tool_calls=forbidden, _flush_messages_to_session_db=forbidden)
        agent._repair_tool_call = types.MethodType(repair_tool_call, agent)
        agent._build_assistant_message = lambda msg, reason: {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': tc.id, 'type': 'function', 'function': {
                'name': tc.function.name, 'arguments': tc.function.arguments}} for tc in msg.tool_calls]}
        message = types.SimpleNamespace(content=None, tool_calls=[types.SimpleNamespace(
            id='fixture_' + str(i), type='function', function=types.SimpleNamespace(name=name, arguments='{}'))
            for i, name in enumerate(calls)])
        messages = []
        verdict = run_tool_round(agent, assistant_message=message, finish_reason='tool_calls', messages=messages,
            conversation_history=[], api_call_count=0, effective_task_id=None, user_message='fixture',
            system_message=None, active_system_prompt='', compression_attempts=0, max_compression_attempts=0,
            final_response=None, failed=False, _turn_exit_reason=None, truncated_tool_call_retries=0,
            current_turn_user_idx=0)
        cases.append(verdict.action == 'continue' and sum(m.get('role') == 'tool' for m in messages) == len(calls))
    return {'all_passed': all(cases) and executor_calls == 0, 'cases': len(cases),
            'executor_calls': executor_calls, 'models_called': 0, 'valid_tool_names': []}


def profile_check(config):
    if config.get('model') != {'default': MODEL, 'provider': 'nvidia',
            'base_url': ENDPOINT.rsplit('/', 2)[0], 'api_mode': 'chat_completions'}:
        raise NativeError('native_model_pin_refused')
    if (config.get('toolsets') or config.get('fallback_providers') or config.get('providers')
            or config.get('mcp_servers') or config.get('hooks') or config.get('plugins', {}).get('enabled')):
        raise NativeError('native_profile_capabilities_refused')
    if config.get('agent', {}).get('api_max_retries') != 0 or config.get('agent', {}).get('auto_recovery_cycles') != 0:
        raise NativeError('native_retry_policy_refused')
    if config.get('memory', {}).get('memory_enabled') is not False or config.get('memory', {}).get('user_profile_enabled') is not False:
        raise NativeError('native_memory_policy_refused')
    if any(slot.get('model') != MODEL or slot.get('provider') != 'nvidia'
           for slot in config.get('auxiliary', {}).values() if isinstance(slot, dict)):
        raise NativeError('native_auxiliary_pin_refused')
    if config.get('kanban', {}).get('dispatch_in_gateway') is not False:
        raise NativeError('native_dispatch_refused')


def prompt_for(packet, role):
    return ('Role: ' + role + '. Independently check this packet; you have no other role answer. '
            'Copy bid for each supplied observation, at most three claims total. Use exact values, units and IDs. '
            'Return JSON with exactly packet_id (from packet), status="review_only", executable=false, '
            'scope="internal_research", claims=[{"observation_id":ID,"field":"bid","value":VALUE,'
            '"unit":"unspecified_source_units","citations":[{"observation_id":ID,"field":"bid"}]}]. '
            'No markdown. Missing bid is null. Packet:\n' + json.dumps(packet, sort_keys=True, separators=(',', ':')))


def main():
    # Keep native logs and exception messages away from receipts. Only two bounded
    # protocol lines use the original stdout; no request/response headers are logged.
    if sys.argv[1:] not in ([], ['--self-test'], ['--offline-replay']):
        return 1
    offline = '--offline-replay' in sys.argv
    protocol = sys.stdout
    null = open(os.devnull, 'w')  # noqa: SIM115 - closed by protocol finally
    sys.stdout = sys.stderr = null
    local = threading.local()
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    def socket_gate(original):
        def guarded(self, *args, **kwargs):
            if not getattr(local, 'allowed', False):
                raise NativeError('non_primary_network_refused')
            return original(self, *args, **kwargs)
        return guarded
    socket.socket.connect = socket_gate(original_connect)
    socket.socket.connect_ex = socket_gate(original_connect_ex)
    result = {'success': False, 'native_valid_tool_names': [], 'http_request_count': 0,
              'blocked_http_attempt_count': 0, 'cost_usd': None, 'cost_status': 'unknown', 'usage': {}}
    agent, guard = None, None
    sentinel, sentinel_bytes = None, None
    try:
        sys.path.insert(0, str(NATIVE_SOURCE))
        import hermes_bootstrap  # noqa: F401
        import httpx
        if '--self-test' in sys.argv:
            proof = rejection_fixture()
            protocol.write(json.dumps(proof) + '\n')
            protocol.flush()
            return 0 if proof['all_passed'] else 1
        body = sys.stdin.buffer.readline(MAX_INPUT + 1)
        if len(body) > MAX_INPUT or not body.endswith(b'\n'):
            raise NativeError('role_input_limit')
        supplied = json.loads(body)
        role, packet = supplied['role'], supplied['packet']
        fault = supplied.get('offline_fault') if offline else None
        if fault not in (None, 'timeout', 'rate_limit'):
            raise NativeError('offline_fault_refused')
        if role not in ('research', 'audit') or not isinstance(packet, dict):
            raise NativeError('role_input_refused')
        profile = Path(os.environ['HERMES_HOME'])
        if profile != Path('/Users/nav/.hermes/profiles') / ('floww-' + role):
            raise NativeError('scoped_profile_refused')
        sentinel = profile / 'ESTOP'
        sentinel_bytes = sentinel.read_bytes()
        def restore_pause():
            fd = os.open(str(sentinel), os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(sentinel_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        def stop(signum, frame):
            raise NativeError('native_deadline_or_termination')
        signal.signal(signal.SIGALRM, stop)
        signal.signal(signal.SIGTERM, stop)
        signal.alarm(35)
        parent_pid = os.getppid()
        def watch_parent():
            while True:
                time.sleep(.2)
                if os.getppid() != parent_pid:
                    with contextlib.suppress(Exception):
                        restore_pause()
                    os._exit(1)
        threading.Thread(target=watch_parent, daemon=True).start()
        key = 'offline-fixture-secret' if offline else None
        # Parse only the exact scoped key; do not source shell or copy .env.
        for line in ([] if offline else (profile / '.env').read_text().splitlines()):
            if line.startswith('NVIDIA_API_KEY='):
                key = line.partition('=')[2].strip().strip('"\'')
                break
        if not key or '\n' in key or len(key) > 4096:
            raise NativeError('scoped_credential_absent')
        prompt = prompt_for(packet, role)
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]
        guard = WireGuard(key, messages)
        original_send = httpx.Client.send
        def guarded_send(client, request, *args, **kwargs):
            guard.admit(str(request.url), request.method, request.content)
            if offline:
                if fault == 'timeout':
                    guard.transport_error_type = 'ReadTimeout'
                    raise httpx.ReadTimeout('Offline fixture timeout', request=request)
                if fault == 'rate_limit':
                    guard.http_status = 429
                    return httpx.Response(429, json={'error': {'message': 'Offline fixture rate limit',
                        'type': 'rate_limit_error'}}, request=request)
                guard.http_status = 200
                guard.finish_reason = 'stop'
                claims = [{'observation_id': obs['observation_id'], 'field': 'bid',
                    'value': obs['fields']['bid']['value'], 'unit': obs['fields']['bid']['unit'],
                    'citations': [{'observation_id': obs['observation_id'], 'field': 'bid'}]}
                    for obs in packet['observations'][:3]]
                copied = {'packet_id': packet['packet_id'], 'status': 'review_only', 'executable': False,
                          'scope': 'internal_research', 'claims': claims}
                fake = {'id': 'offline-fixture', 'object': 'chat.completion', 'created': 1, 'model': MODEL,
                        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(copied)},
                                     'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
                return httpx.Response(200, json=fake, request=request)
            request.headers['Authorization'] = 'Bearer ' + key
            request.extensions['timeout'] = {'connect': 5., 'read': 25., 'write': 5., 'pool': 2.}
            kwargs.update(follow_redirects=False, stream=True)
            local.allowed = True
            try:
                response = original_send(client, request, *args, **kwargs)
                guard.http_status = response.status_code
                data = bytearray()
                try:
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_REPLY:
                            raise NativeError('native_response_limit')
                finally:
                    response.close()
                if response.status_code == 200:
                    with contextlib.suppress(ValueError, TypeError, KeyError, IndexError):
                        observed = json.loads(data)
                        reason = observed['choices'][0].get('finish_reason')
                        guard.finish_reason = reason if reason in ('stop', 'length', 'tool_calls', 'content_filter') else 'unknown'
                        guard.response_usage = {name: value for name, value in observed.get('usage', {}).items()
                            if name in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                            and type(value) is int and 0 <= value <= 10 ** 7}
                return httpx.Response(response.status_code, headers={'Content-Type': 'application/json'},
                                      content=bytes(data), request=request)
            except httpx.TransportError as exc:
                guard.transport_error_type = type(exc).__name__
                raise
            finally:
                local.allowed = False
        async def reject_async(*args, **kwargs):
            guard.blocked += 1
            raise NativeError('async_http_refused')
        httpx.Client.send, httpx.AsyncClient.send = guarded_send, reject_async
        import agent.usage_pricing as pricing
        from agent.estop import is_engaged
        from hermes_cli.config import load_config_readonly
        # Runtime-local metadata adapter: native estimate_usage_cost returns its
        # normal unknown CostResult, without fetching endpoint/models pricing.
        pricing.get_pricing_entry = lambda *args, **kwargs: None
        from run_agent import AIAgent
        config = load_config_readonly()
        profile_check(config)
        if not is_engaged():
            raise NativeError('native_preflight_not_held')
        proof = rejection_fixture()
        if not proof['all_passed']:
            raise NativeError('native_tool_rejection_failed')
        agent = AIAgent(api_key='parent-scoped-transport-only', base_url=ENDPOINT.rsplit('/', 2)[0],
            provider='nvidia', requested_provider='nvidia', api_mode='chat_completions', model=MODEL,
            max_tokens=1024, max_iterations=1, enabled_toolsets=[], disabled_toolsets=config['agent']['disabled_toolsets'],
            quiet_mode=True, verbose_logging=False, save_trajectories=False, platform='cli',
            skip_context_files=True, load_soul_identity=False, skip_memory=True, skip_background_review=True,
            session_db=None, fallback_model={}, credential_pool=None,
            reasoning_config={'enabled': False}, run_budget_seconds=30, cwd=os.getcwd())
        # Do not build native personal/context-rich system text. The boundary
        # subsequently verifies the entire two-message list byte-for-byte.
        agent._build_system_prompt = lambda *args, **kwargs: SYSTEM
        agent._disable_streaming = True
        if (agent.max_tokens != 1024 or agent.max_iterations != 1 or agent.tools or agent.valid_tool_names
            or agent._api_max_retries != 1 or agent._auto_recovery_cycles != 0
            or getattr(agent.client, 'max_retries', None) != 0
            or agent._session_db is not None or agent._memory_enabled or agent._user_profile_enabled
            or not agent.skip_context_files or not agent.skip_background_review):
            raise NativeError('native_effective_envelope_refused')
        source_files = ['run_agent.py', 'agent/agent_init.py', 'agent/turn_tool_validation.py',
                        'agent/turn_tool_round.py', 'agent/client_lifecycle.py', 'agent/usage_pricing.py']
        ready = {'phase': 'ready', 'bounded': True, 'native_class': 'run_agent.AIAgent',
                 'native_valid_tool_names': [], 'advertised_tools': 0, 'output_cap': 1024,
                 'native_total_attempts': 1, 'sdk_retries': 0, 'auto_recovery_cycles': 0,
                 'max_iterations': 1, 'streaming': False, 'offline_replay': offline, 'tool_rejection_passed': proof['all_passed'],
                 'session_db': False, 'memory': False, 'personal_context': False,
                 'pricing_lookup': 'disabled_runtime_adapter_cost_unknown',
                 'native_source_hash': hashlib.sha256(b''.join((NATIVE_SOURCE / p).read_bytes() for p in source_files)).hexdigest()}
        protocol.write(json.dumps(ready) + '\n')
        protocol.flush()
        if sys.stdin.readline(16).strip() != 'RUN' or is_engaged():
            raise NativeError('role_not_admitted')
        guard.phase = 'run'
        answer = agent.run_conversation(prompt, system_message=SYSTEM)
        result['native_failed'] = answer.get('failed') is not False
        result['usage'] = {name: answer[name] for name in ('input_tokens', 'output_tokens', 'reasoning_tokens',
            'total_tokens', 'api_calls', 'cache_read_tokens', 'cache_write_tokens')
            if type(answer.get(name)) is int and 0 <= answer[name] <= 10 ** 7}
        text = answer.get('final_response') or ''
        if not isinstance(text, str) or len(text.encode()) > 32 * 1024:
            raise NativeError('model_output_limit')
        try:
            result['response'] = json.loads(text)
        except (ValueError, RecursionError):
            raise NativeError('model_json_refused') from None
        result['usage'] = {name: answer[name] for name in ('input_tokens', 'output_tokens', 'reasoning_tokens',
            'total_tokens', 'api_calls', 'cache_read_tokens', 'cache_write_tokens')
            if type(answer.get(name)) is int and 0 <= answer[name] <= 10 ** 7}
        result['success'] = result['native_failed'] is False and guard.requests == 1 and guard.blocked == 0
    except BaseException as exc:
        result['exception_type'] = type(exc).__name__
        if isinstance(exc, NativeError):
            result['refusal_code'] = str(exc)
    finally:
        if sentinel is not None and sentinel_bytes is not None:
            with contextlib.suppress(Exception):
                restore_pause()
        signal.alarm(0)
        if agent is not None:
            with contextlib.suppress(Exception):
                agent.close()
        if guard is not None:
            result['http_request_count'] = guard.requests
            result['blocked_http_attempt_count'] = guard.blocked
            result['wire_refusals'] = guard.refusals[:8]
            result['transport_error_type'] = guard.transport_error_type
            result['http_status'] = guard.http_status
            result['finish_reason'] = guard.finish_reason
            result['response_usage'] = guard.response_usage
            result['blocked_origins'] = guard.blocked_origins
        result['offline_replay'] = offline
        if '--self-test' not in sys.argv:
            protocol.write(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
            protocol.flush()
        null.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
