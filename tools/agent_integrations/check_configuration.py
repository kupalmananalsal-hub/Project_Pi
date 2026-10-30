"""Check that project-local agent configuration is inert, documented and credential-free."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}'),
)
PRIVATE_SUFFIXES = {'.wav', '.flac', '.mp3', '.pmdl', '.umdl', '.onnx', '.tflite', '.keras'}


def secret_hits(text: str) -> list[str]:
    return [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(text)]


def tracked_files(root: Path = ROOT) -> list[str]:
    result = subprocess.run(['git', 'ls-files'], cwd=root, check=True, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def check(root: Path = ROOT) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name in ('AGENTS.md', 'CLAUDE.md', 'docs/agent_integrations/policy.md',
                 'docs/agent_integrations/README.md', 'tools/agent_integrations/ssh-read-only.example.json'):
        if not (root / name).is_file():
            errors.append('missing required file: ' + name)
    for activating in ('.mcp.json', '.claude/settings.json', '.claude/settings.local.json'):
        if (root / activating).exists():
            errors.append('activation config must not be committed: ' + activating)
    allowed_roots = (root / '.agents', root / '.claude', root / 'docs/agent_integrations', root / 'tools/agent_integrations')
    candidates = [root / 'AGENTS.md', root / 'CLAUDE.md']
    for directory in allowed_roots:
        if directory.exists():
            candidates.extend(directory.rglob('*'))
    for path in candidates:
        if not path.is_file() or '.git' in path.parts or 'build' in path.parts:
            continue
        if path.suffix.lower() in PRIVATE_SUFFIXES:
            errors.append('prohibited binary/private artifact: ' + path.relative_to(root).as_posix())
            continue
        if path.suffix.lower() in {'.md', '.py', '.json', '.yaml', '.yml', '.txt'}:
            try:
                hits = secret_hits(path.read_text(encoding='utf-8'))
            except UnicodeDecodeError:
                errors.append('non-UTF-8 text candidate: ' + path.relative_to(root).as_posix())
                continue
            if hits:
                errors.append('possible credential in: ' + path.relative_to(root).as_posix())
    try:
        changed = subprocess.run(['git', 'status', '--porcelain'], cwd=root, check=True,
                                 capture_output=True, text=True).stdout.splitlines()
        for record in changed:
            path = record[3:]
            if ' -> ' in path:
                path = path.rsplit(' -> ', 1)[-1]
            if Path(path).suffix.lower() in PRIVATE_SUFFIXES:
                errors.append('new prohibited binary/private artifact: ' + path)
    except (OSError, subprocess.CalledProcessError) as exc:
        warnings.append('could not inspect tracked files: ' + type(exc).__name__)
    return {'errors': errors, 'warnings': warnings}


def main() -> int:
    result = check()
    print(json.dumps(result, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
