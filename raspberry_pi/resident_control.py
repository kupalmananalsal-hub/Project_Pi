"""Opt-in, ephemeral TEST control plane. No alert-store, thermal or network imports.

The lease bound deliberately has NO default. IPC requires an administrator-created
private directory shared only by backend and KWS service accounts (same uid).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import stat
import threading
import time
import uuid
from dataclasses import dataclass


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class Settings:
    test_mode: bool = False
    mute_enabled: bool = False
    max_seconds: float | None = None
    directory: Path | None = None
    credentials: Path | None = None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        test = env.get('PROJECT_PI_RESIDENT_TEST_MODE') == '1' and env.get('WEB_CONCURRENCY', '1') == '1'
        try:
            bound = float(env.get('PROJECT_PI_REMOTE_MUTE_MAX_SECONDS', ''))
            if not math.isfinite(bound) or bound <= 0:
                bound = None
        except (ValueError, TypeError, OverflowError):
            bound = None
        directory = env.get('PROJECT_PI_REMOTE_MUTE_DIR')
        enabled = test and env.get('PROJECT_PI_REMOTE_MUTE_ENABLED') == '1' and bound is not None and bool(directory)
        return cls(test, bool(enabled), bound, Path(directory) if directory else None,
                   Path(env['PROJECT_PI_RESIDENT_CREDENTIALS']) if env.get('PROJECT_PI_RESIDENT_CREDENTIALS') else None)


class MuteFiles:
    """Fixed-name, size-bounded IPC. Never creates directories or follows links."""
    def __init__(self, directory):
        self.root = Path(directory)

    def safe(self):
        try:
            info = self.root.lstat()
            if not self.root.is_absolute() or not stat.S_ISDIR(info.st_mode):
                return False
            if self.root.resolve() != self.root.absolute():
                return False
            return os.name != 'posix' or (info.st_uid == os.getuid() and info.st_mode & 0o077 == 0)
        except (OSError, ValueError, RuntimeError):
            return False

    def read(self, name):
        if not self.safe():
            return {}
        path = self.root / name
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0)
                         | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > 8192:
                    return {}
                result = json.loads(stream.read(8193))
                return result if isinstance(result, dict) else {}
        except (OSError, ValueError, RecursionError):
            return {}

    def write(self, name, value):
        if not self.safe():
            raise ValueError('private_ipc_directory_unavailable')
        path = self.root / name
        if path.is_symlink():
            raise ValueError('unsafe_ipc_path')
        temporary = self.root / ('.' + uuid.uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, allow_nan=False)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def disabled(self):
        return not self.safe() or (self.root / 'remote-mute.disabled').exists()


class KwsMuteGate:
    """Capture-owner gate; workers serialize recognition with ``lock``.

    On every transition the caller resets all recognizers, drains fallback queues,
    cancels only unapproved recognition candidates, then calls acknowledge().
    Existing authorized alert outboxes are intentionally unrelated.
    """
    def __init__(self, settings=None, *, clock=time.monotonic):
        self.settings = settings or Settings.from_env()
        self.clock = clock
        self.files = MuteFiles(self.settings.directory) if self.settings.mute_enabled else None
        self.worker = uuid.uuid4().hex
        self.epoch = 0
        self.muted = False
        self.request = {}
        self.failed_lease = None
        self.lock = threading.RLock()
        if self.files:
            self.acknowledge()

    def poll(self, *, acknowledge=True):
        with self.lock:
            request = self.files.read('request.json') if self.files else {}
            muted = False
            try:
                if not finite_number(request.get('expires_at')):
                    raise ValueError('invalid_expiry')
                remaining = float(request['expires_at']) - self.clock()
                muted = bool(self.files and not self.files.disabled()
                             and request['worker'] == self.worker
                             and (request.get('worker'), request.get('boot'), request.get('lease_id')) != self.failed_lease
                             and request['active'] is True
                             and 0 < remaining <= self.settings.max_seconds
                             and request.get('lease_id') and request.get('boot'))
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
            if muted != self.muted:
                self.epoch += 1
            self.muted, self.request = muted, request
            if acknowledge:
                self.acknowledge()
            return self.muted

    def acknowledge(self):
        if self.files:
            try:
                self.files.write('ack.json', dict(worker=self.worker, epoch=self.epoch,
                    muted=self.muted, lease_id=self.request.get('lease_id'),
                    boot=self.request.get('boot'), observed_at=self.clock()))
            except (OSError, ValueError):
                # Fail open once. The same failed hold must not mute/reset/drop
                # every subsequent frame, even if its request remains on disk.
                if self.muted:
                    self.failed_lease = (self.request.get('worker'), self.request.get('boot'),
                                         self.request.get('lease_id'))
                    self.muted = False
                    self.epoch += 1

    def accepts(self, packet):
        epoch = packet.get('recognition_epoch')
        return not self.muted and type(epoch) is int and epoch == self.epoch

    def capture_boundary(self, queues, reset_recognition, cancel_candidates):
        """Called after capture read, before processing; drop transition frame too."""
        import queue
        with self.lock:
            previous = self.epoch
            muted = self.poll(acknowledge=False)
            changed = previous != self.epoch
            if changed:
                for fallback in queues:
                    while True:
                        try:
                            fallback.get_nowait()
                        except queue.Empty:
                            break
                reset_recognition()
                cancel_candidates()
            self.acknowledge()
            return muted or changed


class RecognitionPoster:
    """Fence only newly recognized candidates; never touch an authorized outbox."""
    def __init__(self, poster, gate):
        self.poster, self.gate = poster, gate

    def publish(self, *args, **kwargs):
        with self.gate.lock:
            if self.gate.accepts(kwargs.get('extra') or {}):
                return self.poster.publish(*args, **kwargs)


class ControlPlane:
    """Single-process, bounded TEST session store; no durable real-alert effects.

    REST handlers run on the event loop. A process restart invalidates all sessions
    and test events. Only one backend worker may own this optional control plane.
    """
    def __init__(self, settings=None, *, clock=time.monotonic):
        self.settings = settings or Settings.from_env()
        self.clock = clock
        self.boot = uuid.uuid4().hex
        self.sessions = {}
        self.events = []
        self.lease = None
        self.files = MuteFiles(self.settings.directory) if self.settings.mute_enabled else None
        self.locally_disabled = False
        self.main_seen = None
        self.lock = threading.RLock()
        if self.files:
            self._release()

    def authenticate(self, identity, token):
        if not self.settings.test_mode or not isinstance(token, str) or len(token) < 32:
            return False
        credentials = self._credentials()
        expected = credentials.get(identity, '')
        return isinstance(expected, str) and len(expected) == 64 and hmac.compare_digest(
            expected, hashlib.sha256(token.encode()).hexdigest())

    def _credentials(self):
        if not self.settings.credentials:
            return {}
        try:
            path = self.settings.credentials
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                    return {}
                if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                    return {}
                raw = stream.read(65537)
                if len(raw) > 65536:
                    return {}
                credentials = json.loads(raw)
            if not isinstance(credentials, dict):
                return {}
            return {key: value for key, value in credentials.items()
                    if isinstance(key, str) and 1 <= len(key) <= 128 and isinstance(value, str)
                    and len(value) == 64 and all(c in '0123456789abcdef' for c in value)}
        except (OSError, ValueError, AttributeError, RecursionError):
            return {}

    def _release(self):
        self.lease = None
        if self.files:
            try:
                self.files.write('request.json', dict(active=False, boot=self.boot))
            except (OSError, ValueError):
                pass  # Worker independently enforces expiry if the release cannot arrive.

    def _expire(self):
        now = self.clock()
        for session in self.sessions.values():
            if now - session['seen'] > 5:
                session['connected'] = False
        if self.lease and (self.lease['expires_at'] <= now or not self.sessions[self.lease['owner']]['connected']):
            self._release()

    def connect(self, identity):
        if not self.settings.test_mode or not isinstance(identity, str) or not 1 <= len(identity) <= 128:
            raise ValueError('test_mode_or_identity_unavailable')
        with self.lock:
            if self.lease and self.lease['owner'] == identity:
                self._release()
            if identity not in self.sessions and len(self.sessions) >= 16:
                raise ValueError('session_capacity_reached')
            self.sessions[identity] = dict(id=uuid.uuid4().hex, sequence=0, seen=self.clock(),
                                           connected=True, commands={})
            return dict(session_id=self.sessions[identity]['id'], **self.snapshot())

    def heartbeat(self, identity, session_id):
        with self.lock:
            self._expire()
            session = self.sessions.get(identity)
            if not session or session['id'] != session_id or not session['connected']:
                raise ValueError('session_expired_reconnect_required')
            session['seen'] = self.clock()
            return self.snapshot()

    def _worker_ack(self):
        ack = self.files.read('ack.json') if self.files else {}
        worker, epoch, observed = ack.get('worker'), ack.get('epoch'), ack.get('observed_at')
        if (not isinstance(worker, str) or len(worker) != 32
                or any(c not in '0123456789abcdef' for c in worker)
                or type(epoch) is not int or epoch < 0
                or type(ack.get('muted')) is not bool
                or not finite_number(observed)
                or not 0 <= self.clock() - observed < 2):
            return {}
        if ack['muted'] and any(not isinstance(ack.get(key), str) or not ack[key]
                                for key in ('lease_id', 'boot')):
            return {}
        return ack

    def snapshot(self):
        with self.lock:
            self._expire()
            ack = self._worker_ack()
            fresh = bool(ack)
            available = bool(self.files and self._credentials() and not self.files.disabled() and not self.locally_disabled and fresh)
            active = bool(available and self.lease and ack.get('muted') is True
                          and ack.get('worker') == self.lease['worker']
                          and ack.get('lease_id') == self.lease['lease_id'] and ack.get('boot') == self.boot)
            return dict(boot_id=self.boot, test_mode=self.settings.test_mode,
                remote_mute_available=available, remote_microphone_muted=active,
                active_lease_id=self.lease['lease_id'] if self.lease else None,
                mute_ack_valid_for_seconds=max(0.0, min(
                    self.lease['expires_at'] - self.clock(),
                    2 - (self.clock() - float(ack['observed_at'])))) if active else 0.0,
                mute_state='muted' if active else ('resuming' if ack.get('muted') else 'unmuted') if fresh else 'unknown',
                max_lease_seconds=self.settings.max_seconds if available else None,
                resident_connected=any(s['connected'] for s in self.sessions.values()),
                main_connected=self.main_seen is not None and self.clock() - self.main_seen < 5,
                events=[dict(e) for e in self.events])

    def main_snapshot(self):
        with self.lock:
            self.main_seen = self.clock()
            return self.snapshot()

    def command(self, identity, body):
        with self.lock:
            self.heartbeat(identity, body.get('session_id'))
            session = self.sessions[identity]
            cid, seq, action = body.get('command_id'), body.get('sequence'), body.get('action')
            if not isinstance(cid, str) or not 1 <= len(cid) <= 128 or type(seq) is not int:
                raise ValueError('invalid_command_envelope')
            fingerprint = (seq, action, body.get('lease_id'))
            if cid in session['commands']:
                old, result = session['commands'][cid]
                if old != fingerprint:
                    raise ValueError('command_id_conflict')
                return dict(result, **self.snapshot())
            if seq <= session['sequence'] or len(session['commands']) >= 300:
                raise ValueError('stale_sequence_or_session_capacity')
            session['sequence'] = seq
            result = {}
            if action in ('keyword_test', 'full_test'):
                if len(self.events) >= 300:
                    raise ValueError('test_event_capacity_restart_test_session')
                result = dict(event_id='test-' + uuid.uuid4().hex, kind=action, is_test=True,
                              delivery='backend_accepted', owner=identity, session_id=session['id'],
                              source='resident_test', command_id=cid, sequence=seq,
                              created_epoch_seconds=time.time(), boot_id=self.boot)
                self.events.append(result.copy())
            elif action == 'mute_start':
                if not self.snapshot()['remote_mute_available'] or self.lease:
                    raise ValueError('remote_mute_unavailable_or_busy')
                ack = self._worker_ack()
                if not ack:
                    raise ValueError('remote_mute_worker_unavailable')
                self.lease = dict(lease_id=uuid.uuid4().hex, owner=identity, session_id=session['id'],
                    worker=ack['worker'], boot=self.boot, active=True,
                    expires_at=self.clock() + self.settings.max_seconds)
                self.files.write('request.json', self.lease)
                result['lease_id'] = self.lease['lease_id']
            elif action in ('mute_renew', 'mute_end'):
                if not self.lease or self.lease['owner'] != identity or self.lease['session_id'] != session['id'] or body.get('lease_id') != self.lease['lease_id']:
                    raise ValueError('stale_or_foreign_lease')
                if action == 'mute_end':
                    self._release()
                elif self.snapshot()['remote_mute_available']:
                    self.lease['expires_at'] = self.clock() + self.settings.max_seconds
                    self.files.write('request.json', self.lease)
                else:
                    self._release()
                    raise ValueError('remote_mute_unavailable')
            elif action == 'disconnect':
                if self.lease and self.lease['owner'] == identity:
                    self._release()
                session['connected'] = False
            else:
                raise ValueError('unknown_action')
            session['commands'][cid] = (fingerprint, result.copy())
            return dict(result, **self.snapshot())

    def present(self, event_id, disposition):
        if disposition not in ('presented', 'user_acknowledged', 'deferred_real_emergency'):
            raise ValueError('invalid_test_disposition')
        with self.lock:
            for event in self.events:
                if event['event_id'] == event_id:
                    if event['delivery'] != 'user_acknowledged':
                        event['delivery'] = disposition
                    return self.snapshot()
            raise ValueError('unknown_test_event')

    def disable_mute(self):
        with self.lock:
            self.locally_disabled = True
            self._release()
            if self.files:
                self.files.write('remote-mute.disabled', {})
            return self.snapshot()
