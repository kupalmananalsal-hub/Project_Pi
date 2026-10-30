# Installation and compatibility guide

## What is installed by this PR

Only text instructions and Python scripts tracked in this repository. There is no
automatic installation or activation. Codex discovers project skills from
`.agents/skills`; Claude Code supports project skills in `.claude/skills`. This
layout follows the official [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skills documentation](https://code.claude.com/docs/en/skills).

`python tools/agent_integrations/validate_skills.py` validates the repository
format, but it is not a claim that either interactive runtime has loaded a skill.
Use each product's own skill listing/diagnostic feature if you need runtime proof.

## Tooling baseline

The development machine used for review had Python available plus local Codex CLI
and Claude Code executables. Their presence is not a deployment prerequisite and
no global settings were changed. Project_Pi itself remains the authority for its
Python and Flutter dependencies.

## Remote Pi diagnostic opt-in

1. Verify the Pi owner authorizes a read-only connection and independently verify
   its host key out of band.
2. Copy `tools/agent_integrations/ssh-read-only.example.json` outside the
   repository, replace only the bracketed placeholders, and keep `enabled` false
   until this task has explicit approval.
3. Use a non-root account, a dedicated least-privilege key, and a dedicated
   known-hosts file. Do not copy either credential into the repository.
4. After explicit approval, use only named probes with
   `--approved-read-only --ssh-config ... --host-alias ...`.

The helper forces `StrictHostKeyChecking=yes`, disables password/agent forwarding,
does not use shell interpolation, and has fixed probes. It cannot run arbitrary
remote commands.

## MCP and external plugin opt-in

There is no `.mcp.json`, Claude settings file, hook, marketplace install, or
global configuration in this change. `mcp.optional.example.json` is not a valid
active configuration name. Read the source review and obtain explicit approval
before any manual installation; preserve a rollback plan first.
