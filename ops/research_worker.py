#!/usr/bin/env python3
"""Local saved-evidence producer. No quote refresh, orders, edits or dispatcher.

A durable started receipt is written before inference. Every attempted identity,
including failure/crash, is terminal for automatic replay. Status and daily files
cover this worker only; they do not assert account or whole-board health.
"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import http.client
import json
import os
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

try:
    from .research_intake import IntakeError, compile_snapshot, validate_research
    from .research_native_role import role_view
except ImportError:
    from research_intake import IntakeError, compile_snapshot, validate_research
    from research_native_role import role_view

MODEL = 'minimaxai/minimax-m3.1-flash'
POLICY = 'retrospective-copied-facts-v1;SPY,QQQ;3-rows;2-independent-roles;one-POST-per-role;no-retry'
DEFAULT_STATE = Path.home() / 'Library/Application Support/FLOWW/operations/research'
ADMISSION_STATE = DEFAULT_STATE.parent / 'research-admission'
DAILY_PAIR_LIMIT = 4
MAX_ADMISSIONS = 1024
HERMES_ROOT = Path('/Users/nav/.hermes')
NATIVE_PYTHON = HERMES_ROOT / 'tools/python-3.14.9+20261021-darwin-arm64/bin/python3'
OFFLINE_PYTHON = HERMES_ROOT / 'installs/754b17ae38e8167a/environments/a0c4ec5217bc4b5c9228fc01809ceed0/venv/bin/python'
ROLE_HELPER = Path(__file__).with_name('research_native_role.py')
URL_PATHS = {symbol: '/api/flowseeker/scan-public/observations?ticker=' + symbol + '&limit=3&order=received'
             for symbol in ('SPY', 'QQQ')}
MAX_BODY = 256 * 1024
MAX_OUTPUT = 128 * 1024
MAX_RECEIPTS = 512
ROLE_SECONDS = 38


class WorkerError(ValueError):
    """Stable nonsecret refusal code."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def ensure_dir(path):
    path = Path(path)
    # Reject any existing symlink component, including an ancestor.
    for component in [path, *path.parents]:
        if component.is_symlink():
            raise WorkerError('unsafe_state_directory')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise WorkerError('unsafe_state_directory')
    path.chmod(0o700)
    return path


def read_bytes(path, limit=MAX_BODY):
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise WorkerError('unsafe_input_file')
            body = handle.read(limit + 1)
    except OSError as exc:
        raise WorkerError('input_file_unavailable') from exc
    if len(body) > limit:
        raise WorkerError('input_byte_limit')
    return body


def parse_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise WorkerError('duplicate_json_key')
            result[key] = value
        return result
    try:
        return json.loads(body, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkerError('nonfinite_json')))
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise WorkerError('invalid_json') from exc


def atomic_json(path, value):
    path = Path(path)
    ensure_dir(path.parent)
    if path.is_symlink():
        raise WorkerError('unsafe_state_file')
    body = (canonical(value) + '\n').encode()
    if len(body) > MAX_BODY:
        raise WorkerError('receipt_byte_limit')
    temporary = path.parent / ('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


class Lease:
    def __init__(self, state):
        self.state, self.fd = Path(state), None

    def __enter__(self):
        ensure_dir(self.state)
        self.directory_identity = self.state.stat()
        self.fd = os.open(str(self.state / 'worker.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        info = os.fstat(self.fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            os.close(self.fd)
            self.fd = None
            raise WorkerError('unsafe_lease')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise WorkerError('lease_busy') from None
        try:
            self.check()
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise
        return self

    def check(self):
        """Refuse a removed/replaced lock or directory instead of rebinding it."""
        try:
            directory = self.state.lstat()
            current = (self.state / 'worker.lock').lstat()
            held = os.fstat(self.fd)
            if (any(component.is_symlink() for component in [self.state, *self.state.parents])
                    or not stat.S_ISDIR(directory.st_mode)
                    or (directory.st_dev, directory.st_ino) !=
                        (self.directory_identity.st_dev, self.directory_identity.st_ino)
                    or not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
                    or current.st_nlink != 1 or held.st_nlink != 1
                    or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino)):
                raise WorkerError('lease_identity_changed')
        except OSError as exc:
            raise WorkerError('lease_identity_changed') from exc

    def __exit__(self, *args):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def paused(state):
    state = Path(state)
    return (state / 'PAUSED').exists() or not (state / 'control.json').exists()


def set_paused(state, value):
    state = ensure_dir(state)
    if value:
        atomic_json(state / 'PAUSED', {'paused': True})
    else:
        atomic_json(state / 'control.json', {'schema': 'floww-research-control.v1', 'enabled': True})
        with contextlib.suppress(FileNotFoundError):
            (state / 'PAUSED').unlink()
    return {'status': 'paused' if paused(state) else 'ready', 'scope': 'saved_research_worker_only'}


def rule_digest():
    files = [Path(__file__), ROLE_HELPER, Path(__file__).with_name('research_intake.py')]
    return hashlib.sha256(b''.join(path.read_bytes() for path in files)).hexdigest()


def input_key(packet, rule_hash=None):
    # Observation IDs include source clocks/values; packet_id includes poll time.
    identity = {'observations': sorted(row['observation_id'] for row in packet['observations']),
                'model': MODEL, 'policy': POLICY, 'rules': rule_hash or rule_digest()}
    return hashlib.sha256(canonical(identity).encode()).hexdigest()


def admission_ledger():
    """Read the fixed shared ledger; receipts may be archived, dedupe may not."""
    path = ADMISSION_STATE / 'admission.json'
    if not path.exists() and not path.is_symlink():
        return {'schema': 'floww-research-admission.v1', 'daily_pair_limit': DAILY_PAIR_LIMIT,
                'circuit_parked': False, 'attempts': {}}
    ledger = parse_json(read_bytes(path))
    if (not isinstance(ledger, dict) or ledger.get('schema') != 'floww-research-admission.v1'
            or type(ledger.get('daily_pair_limit')) is not int
            or not 1 <= ledger['daily_pair_limit'] <= DAILY_PAIR_LIMIT
            or type(ledger.get('circuit_parked')) is not bool
            or not isinstance(ledger.get('attempts'), dict)
            or len(ledger['attempts']) > MAX_ADMISSIONS):
        raise WorkerError('invalid_admission_ledger')
    for key, attempt in ledger['attempts'].items():
        if (not re.fullmatch('[a-f0-9]{64}', key) or not isinstance(attempt, dict)
                or attempt.get('status') not in ('started', 'accepted', 'parked')
                or not isinstance(attempt.get('day_utc'), str)
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', attempt['day_utc'])):
            raise WorkerError('invalid_admission_ledger')
    # A durable unfinished attempt is an unknown result, not retry permission.
    if any(attempt['status'] == 'started' for attempt in ledger['attempts'].values()):
        ledger['circuit_parked'] = True
    return ledger


def reserve_pair(ledger, key, now):
    """Called under the shared lease, before any native work or model call."""
    if key in ledger['attempts']:
        return {'status': 'duplicate_no_call', 'input_key': key,
                'previous_status': ledger['attempts'][key]['status'], 'executable': False}
    day = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date().isoformat()  # noqa: UP017 - Python 3.9 host
    reason = None
    if ledger['circuit_parked']:
        reason = 'native_circuit_parked'
    elif ledger['attempts'] and day < max(a['day_utc'] for a in ledger['attempts'].values()):
        reason = 'admission_clock_regressed'
    elif sum(a['day_utc'] == day for a in ledger['attempts'].values()) >= ledger['daily_pair_limit']:
        reason = 'daily_pair_budget_exhausted'
    elif len(ledger['attempts']) >= MAX_ADMISSIONS:
        reason = 'admission_capacity_manual_review_required'
    if reason:
        atomic_json(ADMISSION_STATE / 'admission.json', ledger)
        return {'status': 'parked', 'reason': reason, 'executable': False}
    ledger['attempts'][key] = {'day_utc': day, 'status': 'started'}
    atomic_json(ADMISSION_STATE / 'admission.json', ledger)
    return None


def resume_circuit():
    """Explicit operator action; keeps prepaid budgets and all dedupe identities."""
    with Lease(ADMISSION_STATE) as admission:
        ledger = admission_ledger()
        for attempt in ledger['attempts'].values():
            if attempt['status'] == 'started':
                attempt['status'] = 'parked'
        ledger['circuit_parked'] = False
        admission.check()
        atomic_json(ADMISSION_STATE / 'admission.json', ledger)
    return {'status': 'circuit_resumed', 'scope': 'saved_research_worker_only', 'executable': False}


def validate_saved_page(saved):
    if not isinstance(saved, dict) or not isinstance(saved.get('rows'), list):
        raise WorkerError('invalid_saved_page')
    counts = {}
    for row in saved['rows']:
        if not isinstance(row, list) or not row or row[0] not in URL_PATHS:
            raise WorkerError('symbol_not_allowed')
        counts[row[0]] = counts.get(row[0], 0) + 1
    if len(saved['rows']) > 6 or any(count > 3 for count in counts.values()):
        raise WorkerError('saved_row_limit')
    return saved


def fetch_saved(symbols=('SPY', 'QQQ'), connection_factory=http.client.HTTPConnection):
    if not symbols or len(symbols) > 2 or len(set(symbols)) != len(symbols) or any(s not in URL_PATHS for s in symbols):
        raise WorkerError('symbol_not_allowed')
    pages = []
    deadline = time.monotonic() + 6
    for symbol in symbols:
        connection = connection_factory('127.0.0.1', 8213, timeout=min(2, max(.01, deadline - time.monotonic())))
        try:
            connection.request('GET', URL_PATHS[symbol], headers={'Accept': 'application/json', 'Connection': 'close'})
            response = connection.getresponse()
            if response.status != 200:
                raise WorkerError('saved_endpoint_unavailable')
            if 'application/json' not in response.getheader('Content-Type', ''):
                raise WorkerError('saved_content_type')
            body = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise WorkerError('saved_deadline')
                chunk = response.read1(min(8192, MAX_BODY + 1 - len(body)))
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    raise WorkerError('saved_body_limit')
                if not chunk:
                    break
            if time.monotonic() > deadline:
                raise WorkerError('saved_deadline')
            page = validate_saved_page(parse_json(body))
            if any(row[0] != symbol for row in page['rows']):
                raise WorkerError('saved_symbol_mismatch')
            pages.append(page)
        except (OSError, http.client.HTTPException) as exc:
            raise WorkerError('saved_endpoint_unavailable') from exc
        finally:
            connection.close()
    return pages


def compile_pages(pages, now):
    if not isinstance(pages, list) or not 1 <= len(pages) <= 2:
        raise WorkerError('saved_page_limit')
    # Every original page must pass the pure source/envelope/count/metadata
    # contract before any merge can supply aggregate values.
    admitted = [compile_snapshot(validate_saved_page(page), now) for page in pages]
    if len(pages) == 1:
        return admitted[0]
    # Compile as one page so the pure validator owns the packet digest.
    combined = {'columns': pages[0].get('columns'), 'rows': [], 'count': 0,
                'source': pages[0]['source'], 'live': pages[0]['live'],
                'trade_eligible': pages[0]['trade_eligible'],
                'row_observations': {}, 'quote_truth': {}, 'observations_by_ticker': {}, 'coverage': {}}
    for page in pages:
        validate_saved_page(page)
        if page.get('columns') != combined['columns']:
            raise WorkerError('columns_mismatch')
        combined['rows'].extend(page['rows'])
        for field in ('row_observations', 'quote_truth', 'observations_by_ticker'):
            if not isinstance(page.get(field), dict):
                raise WorkerError('row_metadata_missing')
            overlap = set(combined[field]) & set(page[field])
            if any(combined[field][key] != page[field][key] for key in overlap):
                raise WorkerError('saved_metadata_conflict')
            combined[field].update(page[field])
    combined['count'] = len(combined['rows'])
    validate_saved_page(combined)
    return compile_snapshot(combined, now)


def _child_limits():
    # Darwin rejects a lower address-space limit; parent measures the whole
    # process group's resident memory instead. Other platforms also get RLIMIT_AS.
    if sys.platform != 'darwin':
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    os.umask(0o077)


def _kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Cleanup must not replace the original deadline/refusal exception.
        with contextlib.suppress(OSError):
            process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=1)


def bounded_process(command, initial, *, timeout=ROLE_SECONDS, output_limit=MAX_OUTPUT, env=None,
                    state=None, on_ready=None, cwd=None, memory_limit=2 * 1024 ** 3):
    """Supervise startup stdin, whole-group deadline, memory and output together."""
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, cwd=cwd, start_new_session=True, preexec_fn=_child_limits, bufsize=0)
    selector = selectors.DefaultSelector()
    output, errors = bytearray(), bytearray()
    ready_seen = False
    memory_checked = 0.
    pending = memoryview(initial)
    close_after_write = on_ready is None
    try:
        os.set_blocking(process.stdin.fileno(), False)
        for stream, target in ((process.stdout, output), (process.stderr, errors)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, target)
        if pending:
            selector.register(process.stdin, selectors.EVENT_WRITE, None)
        elif close_after_write:
            process.stdin.close()
        while selector.get_map() or process.poll() is None:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise WorkerError('role_deadline')
            if state is not None and paused(state):
                raise WorkerError('worker_paused')
            if process.poll() is None and time.monotonic() - memory_checked >= .2:
                try:
                    measured = subprocess.run(['/bin/ps', '-axo', 'pgid=,rss='], capture_output=True,
                                              timeout=min(1, remaining))
                except subprocess.TimeoutExpired:
                    raise WorkerError('role_deadline') from None
                if measured.returncode or len(measured.stdout) > 1024 * 1024:
                    raise WorkerError('role_memory_guard_unavailable')
                rss = sum(int(fields[1]) * 1024 for line in measured.stdout.splitlines()
                          if len(fields := line.split()) == 2 and fields[0] == str(process.pid).encode())
                if rss > memory_limit:
                    raise WorkerError('role_memory_limit')
                memory_checked = time.monotonic()
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise WorkerError('role_deadline')
            for key, mask in selector.select(min(.05, remaining)):
                if mask & selectors.EVENT_WRITE:
                    try:
                        written = os.write(key.fileobj.fileno(), pending[:8192])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        raise WorkerError('role_stdin_closed') from None
                    pending = pending[written:]
                    if not pending:
                        selector.unregister(key.fileobj)
                        if close_after_write:
                            process.stdin.close()
                    continue
                try:
                    chunk = os.read(key.fileobj.fileno(), 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                key.data.extend(chunk)
                if len(output) + len(errors) > output_limit:
                    raise WorkerError('role_output_limit')
            if on_ready is not None and not ready_seen and not pending and b'\n' in output:
                if time.monotonic() - started >= timeout:
                    raise WorkerError('role_deadline')
                ready = parse_json(bytes(output).split(b'\n', 1)[0])
                on_ready(ready)
                pending = memoryview(b'RUN\n')
                close_after_write = True
                selector.register(process.stdin, selectors.EVENT_WRITE, None)
                ready_seen = True
        if process.returncode != 0:
            raise WorkerError('role_process_failed')
        return bytes(output)
    finally:
        # Unbuffered pipes cannot flush a pending blocking write during cleanup.
        _kill_group(process)
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            with contextlib.suppress(OSError, ValueError):
                stream.close()


def run_native_role(role, packet, state):
    if role not in ('research', 'audit'):
        raise WorkerError('role_not_allowed')
    # Separate caller state directories still share one exclusive native-role lease.
    profile = HERMES_ROOT / 'profiles' / ('floww-' + role)
    with Lease(profile / '.floww-saved-research-lease'):
        return _run_native_role_held(role, packet, state)


def _run_native_role_held(role, packet, state, *, offline_replay=False, offline_fault=None):
    if role not in ('research', 'audit'):
        raise WorkerError('role_not_allowed')
    if not offline_replay:
        return _run_native_role_process(role, packet, state)
    scratch = ensure_dir(Path(state) / 'scratch')
    with tempfile.TemporaryDirectory(prefix='offline-replay-', dir=str(scratch)) as folder:
        profile = ensure_dir(Path(folder) / 'offline-profile')
        # Copy only the scoped, independently checked configuration, never .env.
        config = read_bytes(HERMES_ROOT / 'profiles' / ('floww-' + role) / 'config.yaml')
        fd = os.open(str(profile / 'config.yaml'), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(config)
        atomic_json(profile / 'ESTOP', {'reason': 'isolated_offline_fixture'})
        return _run_native_role_process(role, packet, state, offline_profile=profile, offline_fault=offline_fault)


def _run_native_role_process(role, packet, state, *, offline_profile=None, offline_fault=None):
    started = time.monotonic()
    offline_replay = offline_profile is not None
    if role not in ('research', 'audit'):
        raise WorkerError('role_not_allowed')
    profile = offline_profile if offline_replay else HERMES_ROOT / 'profiles' / ('floww-' + role)
    if offline_replay and (profile.name != 'offline-profile' or not profile.parent.name.startswith('offline-replay-')
            or profile.resolve() != profile or HERMES_ROOT in profile.parents):
        raise WorkerError('offline_profile_refused')
    sentinel = profile / 'ESTOP'
    if (not offline_replay and (HERMES_ROOT / 'ESTOP').exists()) or not sentinel.exists():
        raise WorkerError('native_role_not_held')
    protected = [HERMES_ROOT / name for name in ('config.yaml', '.env', 'active_profile', 'kanban/current')]
    protected += [profile / 'config.yaml', profile / '.env',
                  HERMES_ROOT / 'profiles' / ('floww-audit' if role == 'research' else 'floww-research') / 'ESTOP']
    if offline_replay:
        protected = []
    before = {str(p): hashlib.sha256(read_bytes(p)).hexdigest() if p.exists() else None for p in protected}
    original_sentinel = read_bytes(sentinel)
    env = {k: v for k, v in os.environ.items() if not re.search('KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION', k, re.I)
           and not k.startswith('HERMES_')}
    env.update(HERMES_HOME=str(profile), HERMES_IGNORE_RULES='1', PYTHONDONTWRITEBYTECODE='1',
               DO_NOT_TRACK='1', NO_PROXY='*')
    if offline_replay:
        env['HOME'] = str(ensure_dir(profile.parent / 'home'))
    for name in list(env):
        if 'PROXY' in name.upper() and name != 'NO_PROXY':
            del env[name]
    scratch = profile.parent if offline_replay else ensure_dir(Path(state) / 'scratch' / role)
    preflight = None
    def ready(message):
        nonlocal preflight
        if message.get('phase') != 'ready' or not message.get('bounded') or message.get('native_valid_tool_names') != [] or not message.get('tool_rejection_passed'):
            raise WorkerError('native_preflight_refused')
        if (not offline_replay and (HERMES_ROOT / 'ESTOP').exists()) or paused(state):
            raise WorkerError('worker_paused')
        # Native resume removes the fleet sentinel too. Never call it: remove only
        # this role sentinel under the worker lease, restoring exact bytes finally.
        sentinel.unlink()
        preflight = message
    try:
        interpreter = OFFLINE_PYTHON if offline_replay else NATIVE_PYTHON
        output = bounded_process([str(interpreter), '-I', str(ROLE_HELPER)] + (['--offline-replay'] if offline_replay else []),
                                 (canonical({'role': role, 'packet': role_view(packet), 'offline_fault': offline_fault}) + '\n').encode(),
                                 env=env, state=state, on_ready=ready, cwd=str(scratch))
        lines = output.splitlines()
        if len(lines) != 2 or preflight is None:
            raise WorkerError('native_protocol_refused')
        result = parse_json(lines[1])
        result['preflight'] = preflight
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return result
    finally:
        # Restoring the existing sentinel is a scoped native pause; no global state.
        fd = os.open(str(sentinel), os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(original_sentinel)
            handle.flush()
            os.fsync(handle.fileno())
        after = {str(p): hashlib.sha256(read_bytes(p)).hexdigest() if p.exists() else None for p in protected}
        if before != after:
            raise WorkerError('protected_native_state_changed')


def _save_summary(state, receipt, now):
    state = Path(state)
    atomic_json(state / 'latest.json', receipt)
    day = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date().isoformat()  # noqa: UP017 - Python 3.9 observer host
    receipts = [parse_json(read_bytes(p)) for p in (state / 'receipts').glob('*.json')]
    today = [r for r in receipts if datetime.datetime.fromtimestamp(
        r.get('finished_at', r.get('started_at', 0)), datetime.timezone.utc).date().isoformat() == day]  # noqa: UP017 - Python 3.9 host
    daily = {'schema': 'floww-research-daily.v1', 'scope': 'saved_research_worker_only', 'day_utc': day,
             'updated_at': now, 'admitted': False, 'active': 0,
             'accepted_pairs': sum(r.get('status') == 'accepted_retrospective_facts' for r in today),
             'parked_pairs': sum(r.get('status') != 'accepted_retrospective_facts' for r in today),
             'last_substantive_progress': max((r.get('finished_at', 0) for r in receipts
                                               if r.get('status') == 'accepted_retrospective_facts'), default=None),
             'accepted_tests': 'see reviewed source receipt; not asserted by this runtime',
             'refused_evidence': [r.get('reason', 'role_refused') for r in receipts if r.get('status') == 'parked'][:64],
             'unresolved_paper_positions': 'not_observed_by_this_worker', 'cost_usd': None, 'cost_status': 'unknown',
             'accepted_output_per_intervention': None, 'first_pass_acceptance': None,
             'repeat_failures': 0, 'automatic_retries': 0, 'rollback_frequency': 'not_observed_by_this_worker',
             'next_action': 'independent_source_and_native_pair_acceptance; board card remains blocked'}
    atomic_json(state / 'daily' / (day + '.json'), daily)


def run_once(state=DEFAULT_STATE, *, saved=None, producer=None, role_runner=run_native_role, now=None):
    state = Path(state)
    real_clock = now is None
    now = time.time() if real_clock else now
    def finish(result, receipt_path=None, persist=True):
        result.setdefault('started_at', now)
        result['finished_at'] = time.time() if real_clock else now
        if receipt_path is not None:
            atomic_json(receipt_path, result)
        if persist:
            _save_summary(state, result, result['finished_at'])
        return result
    if paused(state):
        return finish({'status': 'paused', 'executable': False}, persist=False)
    try:
        with Lease(state), Lease(ADMISSION_STATE) as admission:
            if paused(state):
                return finish({'status': 'paused', 'executable': False}, persist=False)
            ensure_dir(state / 'receipts')
            try:
                pages = [saved] if saved is not None else (producer or fetch_saved)()
                packet = compile_pages(pages, now)
                if not packet['observations']:
                    raise WorkerError('no_admissible_saved_observations')
            except (WorkerError, IntakeError) as exc:
                return finish({'status': 'parked', 'reason': str(exc), 'executable': False})
            key = input_key(packet)
            receipt_path = state / 'receipts' / (key + '.json')
            if receipt_path.exists() or receipt_path.is_symlink():
                old = parse_json(read_bytes(receipt_path))
                duplicate = {'status': 'duplicate_no_call', 'input_key': key,
                             'previous_status': old.get('status'), 'executable': False}
                return finish(duplicate)
            if len(list((state / 'receipts').glob('*.json'))) >= MAX_RECEIPTS:
                return finish({'status': 'parked', 'reason': 'receipt_capacity_manual_archive_required', 'executable': False})
            ledger = admission_ledger()
            admission.check()
            refusal = reserve_pair(ledger, key, now)
            if refusal is not None:
                return finish(refusal)
            receipt = {'schema': 'floww-research-run.v1', 'input_key': key, 'packet_id': packet['packet_id'],
                       'status': 'started', 'started_at': now, 'model': MODEL, 'policy': POLICY,
                       'rule_hash': rule_digest(), 'executable': False, 'scope': 'internal_research',
                       'native_task_status': 'blocked_pending_independent_acceptance',
                       'automatic_retries': 0, 'roles': {}, 'cost_usd': None, 'cost_status': 'unknown'}
            atomic_json(receipt_path, receipt)
            atomic_json(state / 'packets' / (key + '.json'), packet)
            for role in ('research', 'audit'):
                admission.check()
                if paused(state):
                    receipt['reason'] = 'worker_paused'
                    break
                try:
                    view = role_view(packet)
                    native = role_runner(role, view, state)
                    if not isinstance(native, dict):
                        raise WorkerError('native_protocol_refused')
                    validation = validate_research(packet, native.get('response'))
                    selected = {row['observation_id'] for row in role_view(packet)['observations']}
                    if validation.get('accepted') and (len(native['response']['claims']) > 3 or any(
                            claim['observation_id'] not in selected or claim['field'] != 'bid'
                            for claim in native['response']['claims'])):
                        validation = {'accepted': False, 'reason': 'role_view_claim_refused'}
                    # Only bounded local metadata survives, never raw model prose/errors.
                    receipt['roles'][role] = {k: native[k] for k in ('success', 'http_request_count',
                         'blocked_http_attempt_count', 'native_valid_tool_names', 'cost_status', 'usage', 'preflight',
                         'exception_type', 'refusal_code', 'wire_refusals', 'offline_replay', 'elapsed_seconds',
                         'transport_error_type', 'http_status', 'finish_reason', 'response_usage', 'native_failed',
                         'blocked_origins', 'request_body_bytes', 'message_characters', 'response_bytes', 'response_chunks',
                         'sse_events', 'stream_done', 'stream_refusal', 'first_response_byte_seconds',
                         'last_response_byte_seconds') if k in native}
                    receipt['roles'][role]['validation'] = validation
                    if not (native.get('success') is True and native.get('native_failed', False) is False
                            and not native.get('offline_replay') and native.get('http_request_count') == 1
                            and native.get('blocked_http_attempt_count') == 0 and native.get('native_valid_tool_names') == []):
                        receipt['roles'][role]['validation'] = {'accepted': False, 'reason': 'native_envelope_refused'}
                except (WorkerError, OSError, ValueError, TypeError) as exc:
                    receipt['roles'][role] = {'validation': {'accepted': False,
                        'reason': str(exc) if isinstance(exc, WorkerError) else 'role_failed'}}
                admission.check()
                atomic_json(receipt_path, receipt)
            accepted = len(receipt['roles']) == 2 and all(r['validation'].get('accepted') for r in receipt['roles'].values())
            receipt['status'] = 'accepted_retrospective_facts' if accepted else 'parked'
            receipt['reason'] = 'independently_validated_copied_facts' if accepted else receipt.get('reason', 'role_refused')
            ledger['attempts'][key]['status'] = 'accepted' if accepted else 'parked'
            ledger['circuit_parked'] = not accepted
            admission.check()
            atomic_json(ADMISSION_STATE / 'admission.json', ledger)
            return finish(receipt, receipt_path)
    except WorkerError as exc:
        if str(exc) == 'lease_busy':
            return finish({'status': 'busy', 'executable': False}, persist=False)
        raise


def status(state=DEFAULT_STATE):
    state = Path(state)
    if paused(state):
        result = {'status': 'paused', 'scope': 'saved_research_worker_only'}
        if (state / 'latest.json').exists():
            result['last_result'] = parse_json(read_bytes(state / 'latest.json'))
        return result
    path = state / 'latest.json'
    return parse_json(read_bytes(path)) if path.exists() else {'status': 'ready', 'scope': 'saved_research_worker_only'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run-once', 'status', 'pause', 'resume', 'resume-circuit'])
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--saved-input', type=Path, help='Explicit finite offline saved-observation JSON; never a URL or command')
    args = parser.parse_args(argv)
    def terminate(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        if args.action == 'run-once':
            saved = parse_json(read_bytes(args.saved_input)) if args.saved_input else None
            result = run_once(args.state_dir, saved=saved)
        elif args.action == 'status':
            result = status(args.state_dir)
        elif args.action == 'resume-circuit':
            result = resume_circuit()
        else:
            result = set_paused(args.state_dir, args.action == 'pause')
        print(canonical(result))
    except (WorkerError, OSError, ValueError, KeyboardInterrupt) as exc:
        print(canonical({'status': 'parked', 'reason': str(exc) if isinstance(exc, WorkerError) else 'local_operation_failed', 'executable': False}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
