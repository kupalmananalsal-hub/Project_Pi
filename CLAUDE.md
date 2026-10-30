# Project_Pi Claude Code instructions

Read [shared engineering policy](docs/agent_integrations/policy.md).
Project skill entrypoints in `.claude/skills/` reference the canonical
`.agents/skills/` workflows. They install no plugins, hooks or MCP servers.
Use the [toolkit guide](docs/agent_integrations/README.md) as needed.
Preserve `.cursor/`, private data and unrelated PRs. Never merge automatically.
