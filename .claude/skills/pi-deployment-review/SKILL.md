---
name: pi-deployment-review
description: Prepare a read-only Pi deployment preflight and rollback review without deploying.
---

# Shared Project_Pi workflow

Trigger: use for the capability described above. Prerequisites: this repository
checkout and the [canonical skill](../../../.agents/skills/pi-deployment-review/SKILL.md).

Read that canonical skill before acting; it defines the tools, procedure, errors,
verification, expected output, references and approval boundaries for both agents.
Do not duplicate or override it here. This entrypoint executes no scripts/hooks
and grants no tool permissions. Missing canonical source is a blocker.
