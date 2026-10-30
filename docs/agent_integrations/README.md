# Project_Pi embedded engineering toolkit

This is a repository-local, reviewable workflow toolkit for Codex and Claude Code.
It adds no daemon, hook, plugin, MCP server, SSH connection, package, model, or
hardware action. It is deliberately separate from the Phase 4 dataset PR.

The canonical workflows are in `.agents/skills/`; `.claude/skills/` supplies thin
Claude Code project-skill entrypoints pointing at the same content. The eight
workflows cover architecture, safe Pi diagnostics, ReSpeaker audio, KWS/VAD,
multilingual dataset QA, MLX90640 thermal diagnostics, alert delivery, and
deployment review.

## Start safely

Run these local checks from the repository root:

```powershell
python tools/agent_integrations/validate_skills.py
python tools/agent_integrations/check_configuration.py
python tools/agent_integrations/read_only_pi_preflight.py --probe os
python tools/agent_integrations/offline_hil.py thermal-fixture path/to/frame.json
```

The preflight command above only prints a command plan. It does not start a
process or make a network connection. See [policy.md](policy.md) for approval
levels, [security_review.md](security_review.md) for the threat model, and
[installation_guide.md](installation_guide.md) before opting into anything.

## Explicitly optional integrations

No third-party integration is enabled by this change. The pinned source review,
compatibility decisions, and conditions for a manual opt-in are in
[compatibility_matrix.md](compatibility_matrix.md) and
[optional_integrations.md](optional_integrations.md). The examples ending in
`.example.json` are inert documentation, not runtime configuration.

## Scope limits

This toolkit does not retrain or replace KWS/VAD/Vosk/Snowboy models, alter alert
policy, change thermal logic, capture audio, read an I2C sensor, restart services,
flash hardware, deploy, or merge a PR. A physical test is a separate approved
activity and must be reported separately from offline tests.
