---
name: multilingual-dataset-qa
description: Validate multilingual recording labels, provenance and leakage without training.
---

# multilingual-dataset-qa

## Trigger and prerequisites
Use when the user requests this workflow. Start at the repository root and identify
the current branch. Python 3.10+ and the referenced source are required; physical
hardware is optional, never assumed. Missing optional tools are reported as blockers.

## Safe boundaries and approvals
Apply the [shared policy](../../../docs/agent_integrations/policy.md). Default Level 0
is documentation/local analysis. Level 1 needs explicit connection approval;
Level 2 needs explicit capture/sensor-test approval; Level 3 changes and Level 4
deployment need separate reviewed authorization. These instructions grant no shell
permissions. No global installation, private-data upload or automatic merge.

## Required tools and procedure
Use file reads, Git diff and appropriate existing test runners. The bundled Python
helpers are optional and have no import-time hardware actions.

1. Detect the checked-out pipeline before using commands. Main at this toolkit baseline predates PR #6; do not import or merge its code automatically. On main use existing validation and identify its limits. If PR #6 modules exist in a later checkout, use its strict validator/readiness reporter.
2. Preserve the separate local 563-negative corpus and original archives. This isolated tooling checkout contains no copy; do not claim it has been revalidated here. Confirm real positive WAV availability rather than relying on folders.
3. Check en/fil/ceb labels, the 17 configured positives, unknown speakers/sessions/devices, consent/license records, source hashes, parent ancestry, duplicate recordings and official/grouped splits. Unknown positive language or missing provenance requires review.
4. Keep hi/hello/kamusta and other hard negatives separate from positives; target-containing sentences are review candidates, not automatic negatives. Require competent-speaker approval for new Cebuano phrases.
5. Exclude untouched physical holdouts from mining/training and do not equate format validation with listening verification. Do not run training or copy participant data into reports/commits.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
A factual QA report with PASS/FAIL/REVIEW_REQUIRED and data/branch blockers.

## References
- [raspberry_pi/kws/validate_keyword_dataset.py](../../../raspberry_pi/kws/validate_keyword_dataset.py)
- [raspberry_pi/kws/keyword_dataset_common.py](../../../raspberry_pi/kws/keyword_dataset_common.py)
- [docs/agent_integrations/README.md](../../../docs/agent_integrations/README.md)
