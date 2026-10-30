"""Fixed read-only Pi probes. Default is a plan: no subprocess or network access."""
from __future__ import annotations
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

PROBES = {
    'os': ('cat', '/etc/os-release'),
    'kernel': ('uname', '-srmo'),
    'python': ('python3', '--version'),
    'temperature': ('cat', '/sys/class/thermal/thermal_zone0/temp'),
    'memory': ('free', '-m'),
    'storage': ('df', '-h', '/'),
    'services': ('systemctl', 'show', '--no-pager', '--property=Id,ActiveState,SubState,Result', 'thermal-backend.service', 'kws-alert.service'),
    'capture_devices': ('arecord', '-l'),
    'playback_devices': ('aplay', '-l'),
    'audio_cards': ('cat', '/proc/asound/cards'),
    'interfaces': ('find', '/dev', '-maxdepth', '1', '-name', 'i2c-*', '-o', '-name', 'spidev*', '-o', '-name', 'gpiochip*'),
    'overlays': ('grep', '-E', '^[[:space:]]*(dtoverlay|dtparam)=', '/boot/firmware/config.txt'),
    'models': ('find', '/home/thesis/Project_Pi/dataset/audio/openwakeword_models', '-maxdepth', '1', '-type', 'f', '-printf', '%f\n'),
    # Status code only: when API auth is enabled the backend requires a bearer token, which
    # this probe never reads or sends, so the body is discarded and 401 is the expected answer.
    'backend': ('curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '3', '--output', '/dev/null', '--write-out', '%{http_code}', 'http://127.0.0.1:8765/api/status'),
}
LIMIT = 16384


def classify_backend(result):
    """Name what an unauthenticated /api/status request proves, and no more."""
    code = (result.get('output') or '').strip()[-3:]
    if result.get('exit_code') != 0 or not code.isdigit() or code == '000':
        return 'BACKEND_UNREACHABLE'
    if code == '401':
        # Listening and enforcing auth; authenticated application health is still unverified.
        return 'BACKEND_REACHABLE_AUTH_REQUIRED'
    if code == '200':
        # Answered without a token: no-token mode (the default) or a pre-Milestone-1 backend.
        return 'BACKEND_REACHABLE_AUTH_NOT_ENFORCED'
    return 'BACKEND_HTTP_' + code


def bounded_run(argv, timeout=8, limit=LIMIT):
    """Drain bounded bytes concurrently; kill the child on timeout/output overflow."""
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, shell=False)
    chunks = bytearray(); overflow = threading.Event()
    def drain():
        while True:
            block = process.stdout.read(1024)
            if not block: break
            remaining = limit - len(chunks)
            chunks.extend(block[:remaining])
            if len(block) > remaining:
                overflow.set(); process.kill(); break
    thread = threading.Thread(target=drain, daemon=True); thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True; process.kill(); process.wait(timeout=3)
    thread.join(timeout=3)
    process.stdout.close()
    return {'exit_code':process.returncode, 'timeout':timed_out,
            'truncated':overflow.is_set(), 'output':chunks.decode('utf-8', errors='replace')}


def ssh_argv(config, alias, probe, approved=False):
    if probe not in PROBES: raise ValueError('Unknown probe; arbitrary commands are forbidden')
    if not approved or config.get('enabled') is not True:
        raise PermissionError('Remote inspection is disabled; explicit connection approval is required')
    hosts = config.get('hosts', {})
    if alias not in hosts: raise ValueError('Host is not allowlisted')
    host = hosts[alias]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', host['host']):
        raise ValueError('Invalid host; use explicit DNS name or IPv4, not SSH config aliases')
    if host['user'] == 'root' or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',host['user']):
        raise ValueError('A non-root SSH user is required')
    port = host.get('port',22)
    if type(port) is not int or not 1 <= port <= 65535: raise ValueError('Invalid port')
    for key in ('identity_file','known_hosts_file'):
        value=host[key]
        if any(c in value for c in ('"','\n','\r')) or not Path(value).is_absolute() or not Path(value).is_file():
            raise ValueError('Existing absolute key/known-hosts path required: '+key)
    return ['ssh','-F','none','-T','-p',str(port),'-i',host['identity_file'],
            '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+host['known_hosts_file'],
            '-o','GlobalKnownHostsFile=none','-o','UpdateHostKeys=no',
            '-o','IdentitiesOnly=yes','-o','IdentityAgent=none',
            '-o','ForwardAgent=no','-o','ClearAllForwardings=yes',
            '-o','PermitLocalCommand=no','-o','ProxyCommand=none',
            '-o','ConnectTimeout=5','-o','ConnectionAttempts=1',
            '-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no',
            host['user']+'@'+host['host'], shlex.join(PROBES[probe])]


def run_probes(names, config=None, alias=None, approved=False, local=False, runner=bounded_run, log=None):
    if any(n not in PROBES for n in names): raise ValueError('Only fixed read-only probes are permitted')
    if not config and not local:
        return {'mode':'PLAN_ONLY','commands':{n:list(PROBES[n]) for n in names}}
    if local and (not approved or os.name != 'posix'):
        raise PermissionError('Local Pi execution requires explicit approval on Linux/POSIX')
    results={}
    for name in names:
        argv = ssh_argv(config,alias,name,approved) if config is not None else list(PROBES[name])
        started=time.monotonic()
        if shutil.which(argv[0]) is None:
            result={'exit_code':None,'error':'Missing optional executable: '+argv[0]}
        else:
            try: result=runner(argv)
            except OSError as exc: result={'exit_code':None,'error':type(exc).__name__}
        if name == 'backend' and 'error' not in result:
            result['classification'] = classify_backend(result)
        results[name]=result
        if log:
            # No raw command output, host address, credential path or environment in audit log.
            entry={'probe':name,'mode':'ssh' if config else 'local','exit_code':result.get('exit_code'),
                   'timeout':result.get('timeout',False),'truncated':result.get('truncated',False),
                   'elapsed_ms':round((time.monotonic()-started)*1000),'error':result.get('error'),
                   'classification':result.get('classification')}
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('a',encoding='utf-8') as f: f.write(json.dumps(entry)+'\n')
    return {'mode':'SSH_READ_ONLY' if config else 'LOCAL_READ_ONLY','results':results}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',action='append',choices=sorted(PROBES))
    p.add_argument('--ssh-config',type=Path);p.add_argument('--host-alias')
    p.add_argument('--execute-local',action='store_true')
    p.add_argument('--approved-read-only',action='store_true',help='Affirm explicit user permission for this connection; not a substitute for obtaining it')
    a=p.parse_args()
    if a.ssh_config and a.execute_local: p.error('Choose either local or SSH')
    config=json.loads(a.ssh_config.read_text()) if a.ssh_config else None
    try:
        print(json.dumps(run_probes(a.probe or list(PROBES),config,a.host_alias,a.approved_read_only,a.execute_local,
              log=Path(__file__).resolve().parents[2]/'build/agent_integrations/preflight-audit.jsonl'),indent=2))
    except (ValueError,PermissionError,KeyError) as exc: p.error(str(exc))

if __name__=='__main__': main()
