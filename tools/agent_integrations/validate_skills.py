"""Validate the repository-local Codex and Claude Code skill entrypoints."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = tuple(json.loads((ROOT / 'tools/agent_integrations/skill_names.json').read_text(encoding='utf-8')))
REQUIRED_HEADINGS = ('Trigger and prerequisites', 'Safe boundaries and approvals',
                     'Required tools and procedure', 'Errors and verification', 'Expected output')


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', text, re.DOTALL)
    if not match:
        raise ValueError('missing YAML frontmatter')
    values = {}
    for line in match.group(1).splitlines():
        if ':' not in line:
            raise ValueError('malformed frontmatter')
        key, value = line.split(':', 1)
        values[key.strip()] = value.strip()
    return values


def validate_skill(path: Path, expected_name: str, wrapper: bool = False) -> list[str]:
    errors: list[str] = []
    if not path.is_file() or path.is_symlink():
        return ['missing or symlinked SKILL.md']
    text = path.read_text(encoding='utf-8')
    try:
        meta = frontmatter(text)
    except ValueError as exc:
        return [str(exc)]
    if meta.get('name') != expected_name:
        errors.append('frontmatter name does not match directory')
    if not meta.get('description'):
        errors.append('missing description')
    if not wrapper:
        for heading in REQUIRED_HEADINGS:
            if '## ' + heading not in text:
                errors.append('missing section: ' + heading)
    else:
        target = ROOT / '.agents/skills' / expected_name / 'SKILL.md'
        if not target.is_file() or '.agents/skills/' + expected_name + '/SKILL.md' not in text.replace('\\', '/'):
            errors.append('wrapper does not reference canonical skill')
    return errors


def validate(root: Path = ROOT) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for name in NAMES:
        for parent, wrapper in ((root / '.agents/skills', False), (root / '.claude/skills', True)):
            result = validate_skill(parent / name / 'SKILL.md', name, wrapper)
            if result:
                errors[str(parent / name / 'SKILL.md')] = result
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({'skills': len(NAMES), 'valid': not bool(errors), 'errors': errors}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
