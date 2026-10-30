# Optional integrations — not installed

Every item below remains disabled. A manual opt-in requires a source re-review at
the pinned revision, license approval, explicit user approval, and a rollback
plan. Never paste credentials into a command, repository file, issue, or chat.

| Integration | Potential value | Manual opt-in condition | Why it is disabled |
| --- | --- | --- | --- |
| `tomekness/agent-ssh-access`, `zhinkgit/embeddedskills` | SSH/serial helpers | Pi owner approves a least-privilege host/key and static review accepts its installer behavior | Upstream includes setup or command-execution paths; this PR supplies a smaller read-only alternative. |
| `kuochenfu/ai-hil-mcp` | Serial/build/audio HIL MCP concepts | Dedicated bench, user approval, adapter review, no production Pi target | Its serial/flash surfaces can mutate hardware. |
| `ChrisCompton/omniroute` | Model/provider routing proxy | Approved endpoint, data-flow assessment, secret storage outside Git | Proxy can transmit prompts and requires endpoint configuration. |
| `thedotmack/claude-mem`, `rebelytics/one-skill-to-rule-them-all`, `headroomlabs-ai/headroom` | Local memory/observation/context utilities | Privacy review and explicit hook/write approval | They can capture tool context, write memory, or modify agent files. |
| `obra/superpowers`, `anthropics/claude-plugins-official`, `Ormus-Solutions/LibreEmbed-Claude-Code` | Optional Claude/Codex plugin content | Explicit marketplace/plugin approval after reviewing hooks and transitive code | Plugins/hooks are executable code; none is required for the project skills. |

The official Claude marketplace is a reference, not an approval to install a
plugin. If an approved review later chooses a plugin, record the exact package
version/revision and use the product's documented installer. For Codex, inspect
the locally available marketplace before selecting anything; this PR does not add
one. `alphaonedev/raspberry-pi` and `DisruptionEngineer/build-useful-skills` were
not publicly resolvable at review time, so no alternate repository was substituted.
