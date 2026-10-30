---
name: alert-pipeline-verification
description: Verify event-ID classification, durability, replay and app behavior using isolated tests.
---

# Shared Project_Pi workflow

Trigger: use for the capability described above. Prerequisites: this repository
checkout and the [canonical skill](../../../.agents/skills/alert-pipeline-verification/SKILL.md).

Read that canonical skill before acting; it defines the tools, procedure, errors,
verification, expected output, references and approval boundaries for both agents.
Do not duplicate or override it here. This entrypoint executes no scripts/hooks
and grants no tool permissions. Missing canonical source is a blocker.
