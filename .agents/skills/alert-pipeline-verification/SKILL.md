---
name: alert-pipeline-verification
description: Verify event-ID classification, durability, replay and app behavior using isolated tests.
---

# alert-pipeline-verification

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

1. Use temporary SQLite databases and mocked output devices. Read event_id diagnostics and trace detection, POST, backend classification, persistence, publication, WebSocket receive, provider disposition and each output attempt.
2. Run alert decision, event ID, publication/delivery and backend smoke tests. Verify low-confidence repeats do not become critical, repeated IDs do not duplicate handling, and failed stages retain IDs/reasons.
3. Run Flutter authority, runtime output, delivery, recovery and pairing tests. Verify suppression, advisory notices, thermal-confirmed emergencies, current approved voice-only policy and Resident manual controls from current tests, not stale handoffs.
4. Inspect protocol-v2 authentication, SQLite cursors/ACKs and bounded replay eligibility. Do not dump pairing secrets or live history.
5. Report the last successful stage for failing fixtures. No physical sirens, vibration, manual GPIO presses, live alert POSTs or live database writes are authorized by ordinary regression testing.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
Reproducible traces, exact tests and remaining transport/output uncertainty.

## References
- [test/test_alert_decision.py](../../../test/test_alert_decision.py)
- [test/test_alert_delivery.py](../../../test/test_alert_delivery.py)
- [test/alert_authority_test.dart](../../../test/alert_authority_test.dart)
- [test/alert_runtime_execution_test.dart](../../../test/alert_runtime_execution_test.dart)
