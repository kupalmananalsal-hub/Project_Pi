# Source audit method and findings

The machine-readable lock file records 22 requested repositories, canonical URLs,
full commit SHAs, observed licenses and selected files. `audit_sources.py --fetch`
downloads only explicitly named UTF-8 source files from `raw.githubusercontent.com`
at those exact 40-character SHAs, caps each file at 2 MB, rejects traversal and
never executes downloaded code. Evidence is deliberately stored under ignored
`build/agent-audit/` rather than committed.

The reproducible fetch reviewed 99 selected text files across 20 publicly
accessible repositories and reported no retrieval errors. The audit found two public-source blockers: `alphaonedev/raspberry-pi` and
`DisruptionEngineer/build-useful-skills` returned 404. A web search finding with a
similar title is not provenance, so neither was replaced or integrated.

Notable constraints: SSH/serial/flash packages expose host or hardware mutation;
context/memory plugins can retain prompts/tool activity; model-routing can cause
data egress; hooks are executable; legacy ReSpeaker installation instructions can
modify boot overlays, packages, or reboot; and AGPL/GPL/unknown licenses require
separate legal review before copying code. The resulting project-local skills were
written from Project_Pi's current source and public documentation, not copied from
any reviewed repository.

See the exact per-source disposition in the
[compatibility matrix](compatibility_matrix.md), with a separate
[security review](security_review.md).
