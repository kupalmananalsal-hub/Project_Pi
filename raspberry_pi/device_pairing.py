"""Local-operator device enrollment. No hardware, network, or import-time writes."""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
import uuid


class DeviceRegistry:
    def __init__(self, directory=None, *, clock=time.time):
        self.root = Path(directory) if directory else None
        self.clock = clock

    @classmethod
    def from_env(cls):
        return cls(os.getenv('PROJECT_PI_PAIRING_DIR'))

    def safe(self):
        try:
            if not self.root or not self.root.is_absolute() or self.root.resolve() != self.root:
                return False
            info = self.root.lstat()
            if not stat.S_ISDIR(info.st_mode):
                return False
            return os.name != 'posix' or (info.st_uid == os.getuid() and info.st_mode & 0o077 == 0)
        except (OSError, ValueError, RuntimeError):
            return False

    @contextmanager
    def database(self):
        if not self.safe():
            raise ValueError('pairing_private_directory_unavailable')
        path = self.root / 'devices.sqlite3'
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_size > 4*1024*1024)):
            raise ValueError('unsafe_pairing_database')
        db = sqlite3.connect(path, timeout=3)
        try:
            path.chmod(0o600)
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self):
        with self.database() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, role TEXT, verifier TEXT, revoked INTEGER DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, device TEXT, role TEXT, proof TEXT, code TEXT, expires REAL, token TEXT, failures INTEGER DEFAULT 0)')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('pi_id',?)", (uuid.uuid4().hex,))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('window','0')")

    def available(self):
        return bool(self.safe() and (self.root/'devices.sqlite3').is_file())

    @staticmethod
    def identity(value):
        return isinstance(value,str) and re.fullmatch('[0-9a-f]{32}',value) is not None

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def discovery(self):
        if not self.available():
            return dict(protocol=1, service='project-pi', pairing_available=False, enrollment_open=False)
        try:
            with self.database() as db:
                values = dict(db.execute('SELECT key,value FROM meta').fetchall())
                return dict(protocol=1, service='project-pi', pi_id=values['pi_id'],
                            pairing_available=True, enrollment_open=float(values['window']) > self.clock())
        except (ValueError, OSError, sqlite3.Error):
            return dict(protocol=1, service='project-pi', pairing_available=False, enrollment_open=False)

    def open_window(self, seconds):
        if type(seconds) is not int or not 1 <= seconds <= 300:
            raise ValueError('window_must_be_1_to_300_seconds')
        with self.database() as db:
            db.execute("UPDATE meta SET value=? WHERE key='window'", (str(self.clock()+seconds),))

    def request(self, role, identity, proof):
        if role not in ('caregiver','resident') or not self.identity(identity) or not isinstance(proof,str) or not 32 <= len(proof) <= 128:
            raise ValueError('invalid_pairing_request')
        with self.database() as db:
            now=self.clock()
            db.execute('DELETE FROM requests WHERE expires<=?',(now,))
            if float(db.execute("SELECT value FROM meta WHERE key='window'").fetchone()[0]) <= now:
                raise ValueError('local_enrollment_window_closed')
            existing=db.execute('SELECT revoked FROM devices WHERE id=?',(identity,)).fetchone()
            if existing and not existing['revoked']:
                raise ValueError('identity_already_enrolled_revoke_or_restore_original_credential')
            old=db.execute('SELECT * FROM requests WHERE device=?',(identity,)).fetchone()
            if old:
                if old['role']!=role or not hmac.compare_digest(old['proof'],self.digest(proof)):
                    raise ValueError('request_identity_conflict')
                return dict(request_id=old['id'],code=old['code'],expires_in=max(0,old['expires']-now),state='pending')
            if db.execute('SELECT count(*) FROM requests').fetchone()[0]>=32 or db.execute('SELECT count(*) FROM devices').fetchone()[0]>=128:
                raise ValueError('enrollment_capacity_reached')
            rid=uuid.uuid4().hex
            code=f'{secrets.randbelow(1000000):06d}'
            db.execute('INSERT INTO requests(id,device,role,proof,code,expires) VALUES(?,?,?,?,?,?)',
                       (rid,identity,role,self.digest(proof),code,now+180))
            return dict(request_id=rid,code=code,expires_in=180,state='pending')

    def pending(self):
        with self.database() as db:
            return [dict(request_id=r['id'],device_id=r['device'],role=r['role'],code=r['code'],expires_in=max(0,r['expires']-self.clock()))
                    for r in db.execute('SELECT * FROM requests WHERE expires>? AND token IS NULL',(self.clock(),))]

    def approve(self, request_id, code):
        with self.database() as db:
            row=db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if not row or row['expires']<=self.clock() or row['failures']>=8 or not hmac.compare_digest(row['code'],str(code)):
                raise ValueError('request_expired_or_code_mismatch')
            if row['token']:
                return
            token=secrets.token_urlsafe(32)
            db.execute('INSERT OR REPLACE INTO devices VALUES(?,?,?,0)',(row['device'],row['role'],self.digest(token)))
            db.execute('UPDATE requests SET token=? WHERE id=?',(token,request_id))

    def claim(self, request_id, proof):
        if not isinstance(proof,str) or len(proof)>128:
            raise ValueError('invalid_claim')
        invalid=False
        with self.database() as db:
            row=db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if not row or row['expires']<=self.clock() or row['failures']>=8:
                raise ValueError('expired_pairing_request')
            if not hmac.compare_digest(row['proof'],self.digest(proof)):
                db.execute('UPDATE requests SET failures=failures+1 WHERE id=?',(request_id,))
                invalid=True
            elif not row['token']:
                return dict(state='pending',request_id=request_id,code=row['code'])
            else:
                device=db.execute('SELECT * FROM devices WHERE id=?',(row['device'],)).fetchone()
                if not device or device['revoked']:
                    raise ValueError('revoked_device')
                pi_id=db.execute("SELECT value FROM meta WHERE key='pi_id'").fetchone()[0]
                return dict(state='approved',request_id=request_id,pi_id=pi_id,
                            device_id=row['device'],role=row['role'],token=row['token'])
        if invalid:
            raise ValueError('incorrect_claim_proof')

    def enrolled(self, identity):
        if not self.available() or not self.identity(identity):
            return False
        with self.database() as db:
            return db.execute('SELECT 1 FROM devices WHERE id=?',(identity,)).fetchone() is not None

    def authenticate(self, identity, token, role):
        if not self.available() or not self.identity(identity) or not isinstance(token,str) or not 32<=len(token)<=128:
            return False
        try:
            with self.database() as db:
                row=db.execute('SELECT * FROM devices WHERE id=?',(identity,)).fetchone()
                return bool(row and not row['revoked'] and row['role']==role and hmac.compare_digest(row['verifier'],self.digest(token)))
        except (ValueError,OSError,sqlite3.Error):
            return False

    def prove(self, identity, nonce):
        if not self.identity(identity) or not isinstance(nonce,str) or not 32<=len(nonce)<=128:
            raise ValueError('invalid_challenge')
        with self.database() as db:
            row=db.execute('SELECT * FROM devices WHERE id=?',(identity,)).fetchone()
            if not row or row['revoked']:
                raise ValueError('unknown_or_revoked_device')
            pi_id=db.execute("SELECT value FROM meta WHERE key='pi_id'").fetchone()[0]
            message=f'{pi_id}:{identity}:{nonce}'.encode()
            return dict(pi_id=pi_id,proof=hmac.new(bytes.fromhex(row['verifier']),message,'sha256').hexdigest())

    def revoke(self, identity):
        with self.database() as db:
            db.execute('UPDATE devices SET revoked=1 WHERE id=?',(identity,))
            db.execute('DELETE FROM requests WHERE device=?',(identity,))


def main():
    import argparse,json
    p=argparse.ArgumentParser(description='LOCAL operator pairing approval; never runs a network server.')
    p.add_argument('--directory',required=True,type=Path)
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('init'); window=sub.add_parser('open');window.add_argument('--seconds',type=int,required=True)
    sub.add_parser('list')
    approve=sub.add_parser('approve');approve.add_argument('--request',required=True);approve.add_argument('--code',required=True)
    revoke=sub.add_parser('revoke');revoke.add_argument('--device',required=True)
    args=p.parse_args(); r=DeviceRegistry(args.directory)
    if args.action=='init':r.initialize()
    elif args.action=='open':r.open_window(args.seconds)
    elif args.action=='list':print(json.dumps(r.pending(),indent=2))
    elif args.action=='approve':r.approve(args.request,args.code)
    elif args.action=='revoke':r.revoke(args.device)
    print('Local pairing operation complete; no credentials printed.')

if __name__=='__main__':main()
