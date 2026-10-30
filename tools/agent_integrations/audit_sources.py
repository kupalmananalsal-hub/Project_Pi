"""Fetch bounded, SHA-pinned source text for manual review; never execute it."""
import argparse
import concurrent.futures
import hashlib
import json
import re
import urllib.request
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'docs/agent_integrations/sources.lock.json'


def fetch_file(repo, sha, name, opener=urllib.request.urlopen):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('A canonical repository and full reviewed SHA are required')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe source path')
    url = f'https://raw.githubusercontent.com/{repo}/{sha}/{name}'
    request = urllib.request.Request(url, headers={'User-Agent': 'Project-Pi-source-review'})
    with opener(request, timeout=20) as response:
        if not response.geturl().startswith('https://raw.githubusercontent.com/'):
            raise ValueError('Unexpected source redirect')
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Source exceeds review size limit')
    return {'path': name, 'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'text': raw.decode('utf-8')}


def audit(lock, fetch=False):
    cache = ROOT / 'build/agent-audit/sources'
    cache.mkdir(parents=True, exist_ok=True)
    def one(item):
        output = {k:v for k,v in item.items() if k != 'files'}
        output['evidence'] = []
        for name in item.get('files', []):
            try:
                key = hashlib.sha256((item['canonical'] + item['sha'] + name).encode()).hexdigest()
                dest = cache / (key + '.json')
                if fetch:
                    evidence = fetch_file(item['canonical'], item['sha'], name)
                    dest.write_text(json.dumps(evidence), encoding='utf-8')
                elif dest.exists():
                    evidence = json.loads(dest.read_text(encoding='utf-8'))
                else:
                    raise ValueError('Not cached; use --fetch explicitly to read upstream')
                output['evidence'].append({k:v for k,v in evidence.items() if k != 'text'})
            except Exception as exc:
                output['evidence'].append({'path':name,'error':str(exc)})
        return output
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(one, lock))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    results = audit(json.loads(LOCK.read_text(encoding='utf-8')), args.fetch)
    (ROOT/'build/agent-audit/evidence.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps([{'repo':r['requested'], 'files':len(r['evidence']), 'errors':sum('error' in e for e in r['evidence']), 'status':r['status']} for r in results],indent=2))

if __name__ == '__main__':
    main()
