"""One registered FLOWW task, private native edit, immutable external checker.

No source integration or persistent dispatcher. Live admission is single-use and
must bind the reviewed implementation commit, registry and external checker.
"""
from __future__ import annotations

import argparse
import ast
import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from . import coding_admission as a
except ImportError:
    import coding_admission as a

Refusal = a.Refusal
BASE_SHA = '191e3df9ef54db155d512d7e44577fd48188d12c'
SOURCE_SHA256 = '551f66d35d25d6fa5447e4c8f4510b3ce565cf839e9a8b0d75cc5710bd702388'
REGISTRY_VERSION = 'floww-coding-registry.v1'
CHECKER = Path('/Users/nav/floww-continuation-20261107/coding-trusted/check_next_action.py')
CHECKER_SHA256 = '7f08a14078c24795dfa55bbe290be578db36279f6b38b39b9de4753afad4d2b8'
CHECKER_PYTHON = '/Library/Developer/CommandLineTools/usr/bin/python3'
TARGET = 'ops/operations_receipt.py'
ADMISSION_LEDGER = Path('/Users/nav/Library/Application Support/FLOWW/operations/coding-admissions')
ADMISSION_MAX_AGE = 900


@dataclass(frozen=True)
class RegisteredTask:
    task_id: str = 'receipt-next-action-v1'
    paths: tuple[str, ...] = (TARGET,)
    source_sha256: str = SOURCE_SHA256
    checker_sha256: str = CHECKER_SHA256


def registered_task(task_id='receipt-next-action-v1'):
    if task_id != 'receipt-next-action-v1':
        raise Refusal('unregistered task')
    return RegisteredTask()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal('duplicate admission key')
        result[key] = value
    return result


def _regular_bytes(path, limit=65536, private=False):
    """Pin parent and regular single-link file; refuse links, races and FIFOs."""
    path = Path(path)
    parent = a._open_directory(path.parent)
    fd = None
    try:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit
                or (private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) & 0o077))):
            raise Refusal('unsafe checker or admission file')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if a._identity(os.fstat(fd)) != a._identity(before):
            raise Refusal('file identity changed')
        data = os.read(fd, limit + 1)
        if (len(data) != before.st_size or a._identity(os.fstat(fd)) != a._identity(before)
                or a._identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != a._identity(before)):
            raise Refusal('file changed during snapshot')
        return data
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def export_task(source, workspace, base_sha=BASE_SHA):
    """Export only pinned Git-object bytes; working context/config never enters."""
    task = registered_task()
    if base_sha != BASE_SHA or a.git(source, 'rev-parse', base_sha + '^{commit}').strip() != BASE_SHA:
        raise Refusal('unregistered source base')
    entry = a.git(source, 'ls-tree', BASE_SHA, '--', TARGET).strip().split()
    if len(entry) != 4 or entry[0:2] != ['100644', 'blob'] or entry[3] != TARGET:
        raise Refusal('source tree file contract')
    body = a.git(source, 'show', BASE_SHA + ':' + TARGET).encode()
    if digest(body) != task.source_sha256:
        raise Refusal('source blob identity')
    workspace = Path(workspace)
    workspace.mkdir(mode=0o700)
    (workspace / 'ops').mkdir(mode=0o700)
    (workspace / TARGET).write_bytes(body)
    for args in (('init', '-q', '--template='), ('config', 'user.name', 'FLOWW isolated task'),
                 ('config', 'user.email', 'fixture@invalid'), ('add', '--', TARGET),
                 ('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'exact registered source export')):
        a.git(workspace, *args)
    return task_contract(workspace, a.git(workspace, 'rev-parse', 'HEAD').strip())


def task_contract(workspace, exported_sha):
    task = registered_task()
    return a.TaskContract(task.task_id, exported_sha, str(workspace), task.paths,
                          acceptance=task.task_id).validate()


def _selector(text):
    tree = ast.parse(text)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_summarize')
    node = next(n for n in function.body if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == 'unresolved')
    lines = text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1]), ''.join(lines[node.end_lineno:]), node


def validate_candidate(workspace):
    """Reject all edits outside the selector and any executable selector code."""
    files = a._snapshot_bytes(workspace, (TARGET,))
    if set(files) != {TARGET}:
        raise Refusal('candidate outside declared file scope')
    try:
        baseline = _regular_bytes(CHECKER.with_name('operations_receipt.base.py'))
        if digest(baseline) != SOURCE_SHA256:
            raise Refusal('checker baseline changed')
        before, after, _ = _selector(baseline.decode())
        prefix, suffix, selector = _selector(files[TARGET].decode())
        if before != prefix or after != suffix:
            raise Refusal('source patch outside action selector')
        allowed = (ast.If, ast.Compare, ast.Name, ast.Constant, ast.Assign, ast.Subscript,
                   ast.Load, ast.Store, ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.BoolOp,
                   ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.List, ast.Tuple, ast.Set, ast.Is, ast.IsNot)
        nodes = list(ast.walk(selector))
        if len(nodes) > 200:
            raise Refusal('selector complexity cap')
        for node in nodes:
            if not isinstance(node, allowed):
                raise Refusal('unsafe selector grammar')
            if isinstance(node, ast.Name) and node.id not in ('unresolved', 'review', 'fresh', 'watchdog', 'value', 'action'):
                raise Refusal('unsafe selector name')
            if isinstance(node, ast.Assign) and not (len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'action'
                    and isinstance(node.value, ast.Constant) and type(node.value.value) is str):
                raise Refusal('only literal action assignments')
    except (SyntaxError, ValueError, StopIteration, UnicodeError) as exc:
        raise Refusal('selector contract refused') from exc
    return {name: digest(body) for name, body in files.items()}


def checker_profile(workspace):
    # No candidate imports; still deny network, writes and host/account reads.
    profile = '(version 1)(allow default)(deny network*)(deny file-write*)'
    for path in ('/Users', '/Volumes', '/private/etc', '/private/tmp', '/private/var/folders'):
        profile += '(deny file-read* (subpath ' + json.dumps(path) + '))'
    profile += '(allow file-read* (subpath ' + json.dumps(str(workspace)) + '))'
    for path in (CHECKER, CHECKER.with_name('operations_receipt.base.py'), Path('/dev/null')):
        profile += '(allow file-read* (literal ' + json.dumps(str(path)) + '))'
    return profile


def check_candidate(workspace, checker=CHECKER):
    hashes = validate_candidate(workspace)
    if Path(checker) != CHECKER or digest(_regular_bytes(CHECKER)) != CHECKER_SHA256:
        raise Refusal('trusted checker identity refused')
    command = ['/usr/bin/sandbox-exec', '-p', checker_profile(workspace), CHECKER_PYTHON,
               '-I', '-B', str(CHECKER), str(Path(workspace) / TARGET)]
    result = subprocess.run(command, cwd=workspace, env={'PATH': '/usr/bin:/bin'},
                            capture_output=True, timeout=5)
    if len(result.stdout) > 4096 or len(result.stderr) > 4096:
        raise Refusal('checker output cap')
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise Refusal('trusted checker returned invalid result') from exc
    if (result.returncode or set(value) != {'accepted', 'checks', 'candidate_sha256', 'scope'}
            or value['accepted'] is not True or type(value['checks']) is not int or value['checks'] != 772
            or value['candidate_sha256'] != hashes[TARGET]):
        raise Refusal('trusted checker rejected candidate')
    if validate_candidate(workspace) != hashes or digest(_regular_bytes(CHECKER)) != CHECKER_SHA256:
        raise Refusal('candidate or checker changed during verification')
    return value


def task_prompt(source):
    return ("Edit only ops/operations_receipt.py in the disposable workspace. Use edit immediately; "
            "the complete source follows. Change only _summarize's existing action selector. Preserve "
            "unresolved ledger > missing review > stale review > unhealthy/unknown availability precedence. "
            "Within the existing state != 'reviewed' branch select by refusal code priority: "
            "mode_binding_unverified -> verify_liquid_paper_binding; provider_parked -> inspect_parked_provider; "
            "runtime_unverified -> verify_runtime_acceptance; otherwise independent_review_required. "
            "Reviewed stays none. Use only if/elif/else, membership/comparisons and literal action assignments. "
            "Do not change any other bytes, capabilities, tests, configuration or permissions. No shell, "
            "network, extra files, imports or calls. Then finish.\nSOURCE:\n" + source.decode())


def _private_directory(info):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise Refusal('admission ledger must be private and owner controlled')


def _consume_admission(value):
    """One fixed durable namespace, independent of approval/artifact filenames.

    An inode witness in the trusted parent prevents ledger-directory replacement
    from silently resetting consumed IDs. Partial markers/witnesses park work.
    """
    if not re.fullmatch('[a-f0-9]{32}', value.get('admission_id', '')):
        raise Refusal('invalid externally generated admission id')
    ledger = ADMISSION_LEDGER
    parent = a._open_directory(ledger.parent)
    directory = None
    try:
        _private_directory(os.fstat(parent))
        # Serialize first-time directory/witness creation as well as consumption.
        # Otherwise two initial contenders could each park the other's setup.
        try:
            fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal('admission ledger busy; no retry') from exc
        created = False
        witness = ledger.name + '.identity'
        try:
            os.stat(ledger.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.stat(witness, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Refusal('admission ledger identity disappeared; review required')
            try:
                os.mkdir(ledger.name, 0o700, dir_fd=parent)
                created = True
            except FileExistsError:
                pass
        directory = os.open(ledger.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        _private_directory(os.fstat(directory))
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal('admission ledger busy; no retry') from exc
        info = os.fstat(directory)
        identity = {'device': info.st_dev, 'inode': info.st_ino}

        def assert_current():
            current = a._open_directory(ledger)
            try:
                named = os.fstat(current)
                _private_directory(named)
                if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
                    raise Refusal('admission ledger directory identity changed')
            finally:
                os.close(current)
            if json.loads(_regular_bytes(ledger.parent / witness, private=True), object_pairs_hook=_unique) != identity:
                raise Refusal('admission ledger identity mismatch; review required')

        if created:
            fd = os.open(witness, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            with os.fdopen(fd, 'w') as handle:
                handle.write(json.dumps(identity, sort_keys=True) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(parent)
        assert_current()
        try:
            fd = os.open(value['admission_id'] + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
        except FileExistsError as exc:
            raise Refusal('live admission already consumed; review required') from exc
        # Existence alone refuses replay, including zero/partial crash markers.
        with os.fdopen(fd, 'w') as handle:
            marker = os.fstat(handle.fileno())
            handle.write(json.dumps(value, sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
            named = os.stat(value['admission_id'] + '.json', dir_fd=directory, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (marker.st_dev, marker.st_ino) or named.st_nlink != 1:
                raise Refusal('admission consumption marker identity changed')
        os.fsync(directory)
        assert_current()
    except OSError as exc:
        raise Refusal('admission ledger no-follow check refused') from exc
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def _admit_live(path):
    if path is None:
        raise Refusal('explicit reviewed live admission required')
    path = Path(path)
    source = Path(__file__).resolve().parents[1]
    head = a.git(source, 'rev-parse', 'HEAD').strip()
    if a.git(source, 'status', '--porcelain', '--untracked-files=all'):
        raise Refusal('live implementation must be frozen and clean')
    value = json.loads(_regular_bytes(path, private=True), object_pairs_hook=_unique)
    expected = {'schema': 'floww-coding-live-admission.v2', 'task_id': 'receipt-next-action-v1',
                'implementation_commit': head, 'registry': REGISTRY_VERSION, 'base_sha': BASE_SHA,
                'checker_sha256': CHECKER_SHA256, 'max_generations': 3, 'max_output_tokens': 1024,
                'max_seconds': 90, 'max_input_bytes': 65536, 'max_output_bytes': 262144,
                'max_steps': 3, 'approved': True}
    if (type(value) is not dict or set(value) != set(expected) | {'admission_id', 'issued_at', 'expires_at'}
            or any(type(value[name]) is not type(item) or value[name] != item for name, item in expected.items())):
        raise Refusal('live admission identity mismatch')
    if (type(value['admission_id']) is not str or not re.fullmatch('[a-f0-9]{32}', value['admission_id'])
            or type(value['issued_at']) is not int or type(value['expires_at']) is not int
            or not 0 < value['expires_at'] - value['issued_at'] <= ADMISSION_MAX_AGE
            or not value['issued_at'] <= time.time() < value['expires_at']):
        raise Refusal('live admission id or finite validity refused')
    _consume_admission(value)
    return value


def _native(root, workspace, contract, lease, gate, gateway, receipt, profile):
    config = a.native_config(contract, gateway.base_url, gateway.nonce)
    config['agents']['floww_coding']['system'] = 'Repair only the registered action selector. No shell or extra files.'
    env = a.private_environment(root, config, secrets.token_urlsafe(32), gateway.nonce)
    receipt['effective_config'] = config.copy()
    # Nonce is private per run, never a provider credential.
    lease.assert_current()
    process = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', profile, a.BINARY, 'serve', '--stdio',
                                '--port', '0', '--hostname', '127.0.0.1'], cwd=workspace, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    supervisor = a.ProcessSupervisor(process, gate.deadline)
    supervisor.start()
    try:
        url = None
        startup_deadline = min(gate.deadline, time.monotonic() + 15)
        while time.monotonic() < startup_deadline and process.poll() is None:
            for line in bytes(supervisor.chunks['stdout']).splitlines():
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and isinstance(value.get('url'), str):
                        url = value['url']
                except ValueError:
                    pass
            if url:
                break
            time.sleep(.05)
        if not url or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+', url):
            raise Refusal('native startup failed')
        token = base64.b64encode(('opencode:' + env['OPENCODE_PASSWORD']).encode()).decode()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), a.NoRedirect())

        def request(path, body=None):
            lease.assert_current()
            req = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(),
                headers={'Authorization': 'Basic ' + token, 'Content-Type': 'application/json'})
            with opener.open(req, timeout=max(.1, min(3, gate.deadline - time.monotonic()))) as response:
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise Refusal('native API output cap')
                return json.loads(data) if data else None

        query = '?' + urllib.parse.urlencode({'location[directory]': str(workspace)})
        agents = request('/api/agent' + query)['data']
        mcp = request('/api/mcp' + query)['data']
        plugins = request('/api/plugin' + query)['data']
        if (mcp or any(p.get('source', {}).get('type') != 'builtin' for p in plugins)
                or [agent['id'] for agent in agents] != ['floww_coding']):
            raise Refusal('native extension or agent envelope')
        receipt.update(native_agents=agents, native_mcp=mcp, native_plugins=plugins)
        adversary = request('/api/session', {'title': 'non-generative permission probe', 'agent': 'floww_coding',
            'location': {'directory': str(workspace)},
            'permissions': [{'action': '*', 'resource': '*', 'effect': 'allow'}]})['data']['id']
        receipt['native_denials'] = []
        for action, resource in [('shell', 'touch outside'), ('read', '/Users/nav/.ssh/id_ed25519'),
                ('edit', str(root / 'outside')), ('write', str(CHECKER)), ('external_directory', '/Users/nav'),
                ('execute', '*'), ('subagent', 'general'), ('skill', 'untrusted'),
                ('webfetch', 'https://example.invalid'), ('broker_order', '*')]:
            result = request('/api/session/' + adversary + '/permission',
                             {'action': action, 'resources': [resource], 'agent': 'floww_coding'})
            receipt['native_denials'].append({'action': action, 'effect': result['data']['effect']})
            if result['data']['effect'] != 'deny':
                raise Refusal('native deny bypass')
        session = request('/api/session', {'title': 'registered receipt action task', 'agent': 'floww_coding',
            'location': {'directory': str(workspace)}, 'permissions': config['permissions']})['data']['id']
        prompt = task_prompt(a._snapshot_bytes(workspace, (TARGET,))[TARGET])
        receipt.update(prompt_bytes=len(prompt.encode()), prompt_sha256=digest(prompt.encode()))
        request('/api/session/' + session + '/prompt', {'text': prompt})
        receipt['model_input_submitted'] = True
        completed = False
        while time.monotonic() < gate.deadline and process.poll() is None and not gate.stopped:
            messages = request('/api/session/' + session + '/message')
            if any(item.get('type') == 'assistant' and item.get('time', {}).get('completed')
                   and item.get('finish') == 'stop' for item in messages.get('data', [])):
                completed = True
                break
            time.sleep(.1)
        if gate.stopped or supervisor.reason or not completed:
            raise Refusal('native envelope or supervisor refused')
    finally:
        gate.stop('supervisor_finished')
        supervisor.close()
        receipt.update(private_process_reaped=process.poll() is not None,
                       supervisor_reason=supervisor.reason,
                       startup_stderr=bytes(supervisor.chunks['stderr']).decode(errors='replace')[-4000:])


def run_task(source, artifacts, live=False, admission=None, credential_path=None, hostile=False,
             task_id='receipt-next-action-v1'):
    task = registered_task(task_id)
    authorization = None
    if live:
        authorization = _admit_live(admission)
    elif credential_path is not None or admission is not None:
        raise Refusal('offline task cannot use credentials or admission')
    artifacts = Path(artifacts).resolve()
    artifacts.mkdir(mode=0o700, parents=True, exist_ok=False)
    probe_sentinel = artifacts / 'os-outside-sentinel'
    probe_sentinel.write_bytes(b'unchanged\n')
    if any(os.path.lexists(path) for path in a.MANAGED) or digest(_regular_bytes(Path(a.BINARY), 256 * 1024 * 1024)) != a.BINARY_SHA:
        raise Refusal('native binary or managed policy changed')
    if live and not authorization['issued_at'] <= time.time() < authorization['expires_at']:
        raise Refusal('consumed admission expired before credential access')
    credential = a.read_credential(credential_path) if live else None
    receipt = {'schema': 'floww-coding-task-receipt.v1', 'task': task.task_id,
               'registry': REGISTRY_VERSION, 'source_base': BASE_SHA, 'mode': 'live' if live else 'offline',
               'status': 'blocked', 'independent_review': 'pending', 'source_integration': False,
               'publication': False, 'capabilities': {'accounts': False, 'orders': False, 'service_control': False}}
    exchanges = []
    with tempfile.TemporaryDirectory(prefix='floww-product-', dir='/private/tmp') as temporary:
        root = Path(temporary).resolve()
        workspace = root / 'work'
        contract = export_task(source, workspace)
        receipt['contract'] = a.asdict(contract)
        outside = root / 'outside'
        outside.write_bytes(a._snapshot_bytes(workspace, (TARGET,))[TARGET])
        gate = a.RequestGate(contract)
        if live:
            gate.deadline = min(gate.deadline, time.monotonic() + authorization['expires_at'] - time.time())
            receipt['admission'] = authorization

        def offline_transport(body, _key, _timeout):
            exchanges.append(body)
            number = len(exchanges)
            if number == 1:
                path = str(root / 'outside' if hostile else workspace / TARGET)
                replacement = ("    elif value['state'] != 'reviewed':\n"
                    "        if 'mode_binding_unverified' in review['refusal_codes']:\n"
                    "            action = 'verify_liquid_paper_binding'\n"
                    "        elif 'provider_parked' in review['refusal_codes']:\n"
                    "            action = 'inspect_parked_provider'\n"
                    "        elif 'runtime_unverified' in review['refusal_codes']:\n"
                    "            action = 'verify_runtime_acceptance'\n"
                    "        else:\n            action = 'independent_review_required'")
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'receipt_call', 'type': 'function',
                    'function': {'name': 'edit', 'arguments': json.dumps({'path': path,
                    'oldString': "    elif value['state'] != 'reviewed':\n        action = 'independent_review_required'",
                    'newString': replacement})}}]}
                finish = 'tool_calls'
            else:
                delta, finish = {'role': 'assistant', 'content': 'Done.'}, 'stop'
            chunks = [{'id': 'offline', 'object': 'chat.completion.chunk', 'model': a.MODEL,
                'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                {'id': 'offline', 'object': 'chat.completion.chunk', 'model': a.MODEL,
                 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}]
            output = b''.join(b'data: ' + json.dumps(item).encode() + b'\n\n' for item in chunks) + b'data: [DONE]\n\n'
            return 200, 'text/event-stream', output

        with a.WorkspaceLease(contract) as lease:
            def transport(body, key, timeout):
                lease.assert_current()
                if live and not authorization['issued_at'] <= time.time() < authorization['expires_at']:
                    raise Refusal('live admission expired before generation')
                return (a.official_request if live else offline_transport)(body, key, timeout)

            with a.Gateway(gate, credential, transport) as gateway:
                profile = a.sandbox_profile(root, workspace, gateway.server.server_port, (TARGET,))
                (artifacts / 'sandbox.sb').write_text(profile)
                try:
                    receipt['before'] = lease.before
                    probe = subprocess.run(['/usr/bin/sandbox-exec', '-p', profile, CHECKER_PYTHON, '-I', '-B', '-c',
                        "from pathlib import Path\nimport socket\n"
                        "for name in " + repr([str(outside), str(probe_sentinel)]) + ":\n"
                        " try: Path(name).open('ab').write(b'forbidden')\n"
                        " except PermissionError: pass\n"
                        " else: raise SystemExit(40)\n"
                        "try: socket.create_connection(('127.0.0.1', 9),timeout=.2)\n"
                        "except PermissionError: pass\n"
                        "else: raise SystemExit(41)\n"],
                        cwd=workspace, env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=3)
                    if (probe.returncode or digest(outside.read_bytes()) != SOURCE_SHA256
                            or probe_sentinel.read_bytes() != b'unchanged\n'):
                        raise Refusal('OS write or network boundary unproven')
                    receipt['os_outside_writes_and_other_network_denied'] = True
                    _native(root, workspace, contract, lease, gate, gateway, receipt, profile)
                    lease.assert_current()
                    receipt['outside_sentinel_unchanged'] = digest(outside.read_bytes()) == SOURCE_SHA256
                    if not receipt['outside_sentinel_unchanged']:
                        raise Refusal('outside sentinel changed')
                    receipt['changed_paths'] = a.changed_paths(workspace, lease.before, contract)
                    if receipt['changed_paths'] != [TARGET]:
                        raise Refusal('registered target was not changed')
                    receipt['checker'] = check_candidate(workspace)
                    receipt['after'] = validate_candidate(workspace)
                    receipt['status'] = 'source_patch_proof_pass_review_pending'
                except Exception as exc:
                    receipt['reason'] = str(exc) if isinstance(exc, Refusal) else type(exc).__name__
                finally:
                    receipt.update(requests=gate.receipts, gateway_denials=gateway.denials)
                    try:
                        lease.assert_current()
                        validate_candidate(workspace)
                        (artifacts / 'candidate.py').write_bytes(a._snapshot_bytes(workspace, (TARGET,))[TARGET])
                        (artifacts / 'candidate.patch').write_text(a.git(workspace, 'diff', '--', TARGET))
                    except (Refusal, OSError):
                        receipt['unsafe_candidate_not_exported'] = True
    (artifacts / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if not live:
        (artifacts / 'native-requests.json').write_text(json.dumps(exchanges, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--task', default='receipt-next-action-v1')
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--admission')
    parser.add_argument('--credential-file')
    parser.add_argument('--hostile-offline', action='store_true')
    args = parser.parse_args()
    if args.live and args.hostile_offline:
        parser.error('hostile replay is offline only')
    receipt = run_task(args.source, args.artifacts, args.live, args.admission, args.credential_file,
                       args.hostile_offline, args.task)
    print(json.dumps({'status': receipt['status'], 'reason': receipt.get('reason')}))
    return 0 if receipt['status'] == 'source_patch_proof_pass_review_pending' else 1


if __name__ == '__main__':
    raise SystemExit(main())
