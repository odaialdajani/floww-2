#!/usr/bin/env python3
"""Model-free local observer. No execution, account, provider or repair capability."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import uuid

DEFAULT_STATE = Path.home() / 'Library/Application Support/FLOWW/operations'
DEFAULT_RUNTIME = Path.home() / 'Library/Application Support/FLOWW/local'
ENDPOINTS = {
    'backend_version': (8213, '/api/version'),
    'backend_health': (8213, '/health'),
    'frontend': (3000, '/'),
}
PROBE_TIMEOUT = 2.0
MAX_BODY = 256 * 1024
MAX_SNAPSHOTS = 288
EVENT_BYTES = 256 * 1024
STALE_AFTER = 600
CAPABILITIES = {'execution': False, 'liquid': False, 'models': False,
                'provider_reads': False, 'autofix': False, 'service_control': False}


class LeaseBusy(Exception):
    """Another local process owns collection; never replace its result."""


def ensure_private_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('State directories must not be symbolic links')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('State directory ownership is unavailable')
    path.chmod(0o700)
    return path


def _open_owned(path, flags):
    fd = os.open(str(path), flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        os.close(fd)
        raise ValueError('Unsafe state file')
    return fd


class Lease:
    """The kernel releases this single-host lease when its owner exits."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.fd = None

    def __enter__(self):
        ensure_private_dir(self.directory)
        self.fd = _open_owned(self.directory / 'observer.lock', os.O_CREAT | os.O_RDWR)
        os.fchmod(self.fd, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise LeaseBusy()
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def _fsync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_bytes(path, body):
    path = Path(path)
    # A fixed staging name cannot accumulate on repeated process crashes.
    name = '.snapshot.pending' if path.parent.name == 'snapshots' else '.' + path.name + '.pending'
    staging = path.parent / name
    fd = _open_owned(staging, os.O_CREAT | os.O_WRONLY)
    try:
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(staging), str(path))
        _fsync_directory(path.parent)
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            staging.unlink()


def _atomic_json(path, value):
    _atomic_bytes(path, (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode('utf-8'))


def _read_bounded(path, limit, private=False):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Expected a regular file')
        if private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError('State file is not private')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            body = stream.read(limit + 1)
        if len(body) > limit:
            raise ValueError('Local metadata exceeds the bound')
        return body
    finally:
        if fd is not None:
            os.close(fd)


def _within(path, parent):
    return os.path.commonpath([str(path), str(parent)]) == str(parent)


def load_pin(runtime_root=DEFAULT_RUNTIME):
    """Read only runtime identity metadata and its pinned compiled index.html."""
    root = Path(runtime_root)
    try:
        settings = json.loads(_read_bounded(root / 'runtime.json', 65536))
        sha = settings['sha']
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha):
            raise ValueError('Invalid release revision')
        releases = (root / 'releases').resolve(strict=True)
        release = Path(settings['release']).resolve(strict=True)
        if (not _within(release, releases) or release == releases
                or not re.fullmatch('[a-f0-9]{7,40}', release.name)
                or not sha.startswith(release.name)):
            raise ValueError('Unrecognized pinned release')
        index = (release / 'frontend/build/index.html').resolve(strict=True)
        if not _within(index, release):
            raise ValueError('Pinned HTML escaped its release')
        body = _read_bounded(index, MAX_BODY)
        return {'state': 'ok', 'sha': sha, 'release': release.name,
                'frontend_sha256': hashlib.sha256(body).hexdigest()}
    except (OSError, ValueError, TypeError, KeyError):
        return {'state': 'unknown', 'reason': 'pin_unavailable'}


def _paused(state_dir):
    # Any STOP entry, including a dangling link, refuses reads rather than
    # following it or interpreting user text as instructions.
    return os.path.lexists(str(Path(state_dir) / 'STOP'))


def probe_endpoint(name, state_dir):
    """One direct IPv4 HTTP GET. Called in a deadline-controlled child."""
    if name not in ENDPOINTS:
        raise ValueError('Only fixed local endpoints are supported')
    if _paused(state_dir):
        return {'state': 'paused', 'reason': 'stop_sentinel'}
    port, path = ENDPOINTS[name]
    connection = None
    try:
        # HTTPConnection uses no proxy discovery and never follows redirects.
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2.0)
        if _paused(state_dir):
            return {'state': 'paused', 'reason': 'stop_sentinel'}
        connection.request('GET', path, headers={'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = connection.getresponse()
        code = response.status
        if code != 200:
            return {'state': 'failed', 'reason': 'redirect_blocked' if 300 <= code < 400 else 'http_error',
                    'http_status': code}
        encoding = response.getheader('Content-Encoding', '')
        if encoding and encoding.lower() != 'identity':
            return {'state': 'unknown', 'reason': 'unsupported_encoding', 'http_status': code}
        length = response.getheader('Content-Length')
        declared_length = None
        if length is not None:
            try:
                declared_length = int(length)
                if declared_length < 0:
                    raise ValueError('Negative response length')
                if declared_length > MAX_BODY:
                    return {'state': 'unknown', 'reason': 'response_too_large', 'http_status': code}
            except ValueError:
                return {'state': 'unknown', 'reason': 'invalid_response', 'http_status': code}
        if _paused(state_dir):
            return {'state': 'paused', 'reason': 'stop_sentinel'}
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            return {'state': 'unknown', 'reason': 'response_too_large', 'http_status': code}
        if declared_length is not None and len(body) != declared_length:
            return {'state': 'unknown', 'reason': 'truncated_response', 'http_status': code}
        if name == 'frontend':
            return {'state': 'ok', 'sha256': hashlib.sha256(body).hexdigest(), 'http_status': code}
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError('Expected metadata object')
        if name == 'backend_version':
            sha = value.get('sha')
            if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{7,40}', sha):
                raise ValueError('Missing revision')
            return {'state': 'ok', 'sha': sha, 'http_status': code}
        health = value.get('status')
        if not isinstance(health, str) or not health:
            raise ValueError('Missing health status')
        return {'state': 'ok' if health == 'ok' else 'failed',
                'health': 'ok' if health == 'ok' else 'not_ok', 'http_status': code}
    except (socket.timeout, TimeoutError):
        return {'state': 'failed', 'reason': 'transport_timeout'}
    except (OSError, http.client.HTTPException):
        return {'state': 'failed', 'reason': 'transport_unavailable'}
    except (ValueError, TypeError):
        return {'state': 'unknown', 'reason': 'invalid_response'}
    finally:
        if connection is not None:
            connection.close()


def run_probe(name, state_dir):
    """Kill/reap a slow child, bounding even trickled headers or body bytes."""
    if name not in ENDPOINTS:
        raise ValueError('Only fixed local endpoints are supported')
    if _paused(state_dir):
        return {'state': 'paused', 'reason': 'stop_sentinel'}
    command = [sys.executable, '-I', str(Path(__file__).resolve()), '--state-dir', str(state_dir), '_probe', name]
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
    except OSError:
        return {'state': 'unknown', 'reason': 'probe_worker_unavailable'}
    try:
        body, _ = process.communicate(timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return {'state': 'failed', 'reason': 'deadline_exceeded'}
    if process.returncode != 0 or len(body) > 16384:
        return {'state': 'unknown', 'reason': 'probe_worker_failed'}
    try:
        result = json.loads(body)
        if not isinstance(result, dict) or result.get('state') not in ('ok', 'failed', 'unknown', 'paused'):
            raise ValueError('Invalid worker result')
        return result
    except (ValueError, TypeError):
        return {'state': 'unknown', 'reason': 'probe_worker_failed'}


def _iso(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat()


def _identity(pin, checks):
    version = checks.get('backend_version', {})
    frontend = checks.get('frontend', {})
    if pin.get('state') != 'ok' or version.get('state') != 'ok' or frontend.get('state') != 'ok':
        return {'state': 'unknown', 'reason': 'identity_evidence_unavailable'}
    back = version.get('sha', '')
    matched = pin['sha'].startswith(back) and frontend.get('sha256') == pin['frontend_sha256']
    return {'state': 'matched' if matched else 'mismatch', 'expected_sha': pin['sha'],
            'backend_sha': back, 'frontend_sha256': frontend.get('sha256'),
            'expected_frontend_sha256': pin['frontend_sha256']}


def _persist(state_dir, snapshot):
    snapshots = ensure_private_dir(state_dir / 'snapshots')
    sequence = '%020d-%s.json' % (time.time_ns(), uuid.uuid4().hex[:8])
    _atomic_json(snapshots / sequence, snapshot)
    owned = sorted(p for p in snapshots.iterdir() if re.fullmatch(r'[0-9]{20}-[a-f0-9]{8}\.json', p.name))
    for path in owned[:-MAX_SNAPSHOTS]:
        if path.is_file() and not path.is_symlink() and path.stat().st_uid == os.getuid():
            path.unlink()
    _atomic_json(state_dir / 'status.json', snapshot)
    event = {'checked_at': snapshot['checked_at'], 'state': snapshot['state'],
             'identity': snapshot.get('identity', {}).get('state', 'unknown')}
    line = (json.dumps(event, sort_keys=True) + '\n').encode('utf-8')
    event_path = state_dir / 'events.jsonl'
    try:
        prior = _read_bounded(event_path, EVENT_BYTES, private=True)
    except FileNotFoundError:
        prior = b''
    if len(prior) + len(line) > EVENT_BYTES:
        _atomic_bytes(state_dir / 'events.1.jsonl', prior)
        prior = b''
    _atomic_bytes(event_path, prior + line)


def check_once(state_dir=DEFAULT_STATE, runtime_root=DEFAULT_RUNTIME, probe=None, clock=time.time):
    state_dir = ensure_private_dir(state_dir)
    try:
        with Lease(state_dir):
            checks = {}
            pin = load_pin(runtime_root)
            for name in ENDPOINTS:
                if _paused(state_dir):
                    break
                checks[name] = (probe or run_probe)(name, state_dir)
                if checks[name].get('state') == 'paused':
                    break
            identity = _identity(pin, checks)
            pin_after = load_pin(runtime_root)
            if pin != pin_after:
                identity = {'state': 'unknown', 'reason': 'pin_changed_during_check'}
            states = [result.get('state') for result in checks.values()]
            if _paused(state_dir) or 'paused' in states:
                overall = 'paused'
            elif pin != pin_after:
                overall = 'unknown'
            elif 'failed' in states or identity['state'] == 'mismatch':
                overall = 'unhealthy'
            elif len(checks) != len(ENDPOINTS) or 'unknown' in states or identity['state'] != 'matched':
                overall = 'unknown'
            else:
                overall = 'healthy'
            snapshot = {'schema': 'floww-watchdog.v1', 'checked_at': _iso(clock()),
                        'state': overall, 'checks': checks, 'identity': identity,
                        'capabilities': dict(CAPABILITIES),
                        'scope': 'local transport and release identity only'}
            _persist(state_dir, snapshot)
            return status(state_dir, clock=clock)
    except LeaseBusy:
        return {'state': 'busy', 'freshness': 'unknown', 'reason': 'observer_already_running',
                'capabilities': dict(CAPABILITIES)}


def status(state_dir=DEFAULT_STATE, clock=time.time):
    """Read saved evidence only; a previous green sample can become stale."""
    state_dir = Path(state_dir)
    try:
        if state_dir.is_symlink():
            raise ValueError('Unsafe state directory')
        snapshot = json.loads(_read_bounded(state_dir / 'status.json', MAX_BODY, private=True))
        if not isinstance(snapshot, dict) or snapshot.get('schema') != 'floww-watchdog.v1':
            raise ValueError('Invalid saved snapshot')
        sample = datetime.datetime.fromisoformat(snapshot['checked_at'])
        if sample.tzinfo is None:
            raise ValueError('Saved source time has no timezone')
        age = clock() - sample.timestamp()
        snapshot['sample_age_seconds'] = round(age, 3) if age >= 0 else None
        snapshot['freshness'] = ('stale' if age > STALE_AFTER else 'fresh') if age >= 0 else 'unknown'
    except (OSError, ValueError, TypeError, KeyError):
        snapshot = {'state': 'unknown', 'freshness': 'unknown', 'sample_age_seconds': None,
                    'reason': 'sample_unavailable', 'capabilities': dict(CAPABILITIES)}
    stopped = _paused(state_dir)
    snapshot['desired_state'] = 'paused' if stopped else 'running'
    if stopped:
        snapshot['state'] = 'paused'
        snapshot['reason'] = 'stop_sentinel'
    elif snapshot.get('state') == 'paused':
        snapshot['state'] = 'unknown'
        snapshot['reason'] = 'check_needed_after_resume'
    return snapshot


def pause(state_dir=DEFAULT_STATE, clock=time.time):
    state_dir = ensure_private_dir(state_dir)
    # Publish before waiting for a collector: it checks this between probes.
    _atomic_json(state_dir / 'STOP', {'paused_at': _iso(clock())})
    return status(state_dir, clock=clock)


def resume(state_dir=DEFAULT_STATE, clock=time.time):
    state_dir = ensure_private_dir(state_dir)
    try:
        with Lease(state_dir):
            with contextlib.suppress(FileNotFoundError):
                (state_dir / 'STOP').unlink()
            _fsync_directory(state_dir)
    except LeaseBusy:
        return {'state': 'busy', 'freshness': 'unknown', 'reason': 'observer_already_running',
                'capabilities': dict(CAPABILITIES)}
    return status(state_dir, clock=clock)


def exit_code(result):
    state = result.get('state')
    if state == 'paused':
        return 3
    if state == 'busy':
        return 4
    if result.get('freshness') == 'unknown':
        return 2
    if result.get('freshness') == 'stale':
        return 5
    return {'healthy': 0, 'unhealthy': 1}.get(state, 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE,
                        help='private observer state directory (no URL configuration)')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='collect one bounded local sample')
    check.add_argument('mode', choices=['once'])
    for name in ['status', 'pause', 'resume']:
        commands.add_parser(name)
    child = commands.add_parser('_probe', help=argparse.SUPPRESS)
    child.add_argument('endpoint', choices=list(ENDPOINTS))
    args = parser.parse_args(argv)
    try:
        if args.command == '_probe':
            result = probe_endpoint(args.endpoint, args.state_dir)
            print(json.dumps(result, sort_keys=True))
            return 0
        action = {'check': check_once, 'status': status, 'pause': pause, 'resume': resume}[args.command]
        result = action(args.state_dir)
    except (OSError, ValueError, TypeError):
        result = {'state': 'unknown', 'freshness': 'unknown', 'reason': 'observer_state_unavailable',
                  'capabilities': dict(CAPABILITIES)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code(result)


if __name__ == '__main__':
    sys.exit(main())
