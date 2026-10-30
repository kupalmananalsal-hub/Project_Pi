# Security review

## Threat model

Project_Pi handles safety-related alerts, local speech/thermal data and a Raspberry
Pi. The main risks are accidental alert-policy/model changes, microphone or dataset
disclosure, hostile host-key replacement, remote command execution, hardware
mutation, supply-chain plugins, prompt/context egress, and secrets in Git.

## Controls implemented here

- No external repository code is vendored or executed; source review is SHA-pinned,
  bounded and opt-in.
- No MCP config, plugin, hook, marketplace, remote host, credential or global
  setting is created.
- The SSH helper is plan-only by default; execution additionally needs explicit
  approval, `enabled: true`, an allowlisted host, non-root user, existing absolute
  key/known-hosts paths, strict host-key checking and a fixed probe name.
- Fixed subprocesses use argument arrays, `shell=False`, timeout/output bounds and
  do not accept arbitrary remote commands.
- Offline HIL consumes finite fixture data/files only and cannot open hardware.
- Configuration checks reject common key/token patterns and tracked dataset audio or
  model artifacts. These checks are defense in depth, not a replacement for secret
  scanning or access controls.

## Residual risks and required approvals

Host compromise, a stolen dedicated key, malformed device output, weaknesses in
third-party tools, and physical hardware faults remain possible. Any Level 2+
operation needs an owner-approved test plan. Never use `sudo`, reboot, install a
driver, write GPIO/I2C, capture audio, modify boot config, upload data, flash, or
restart a service from this toolkit. Separate code review is required for every
change to alert policy, KWS model, VAD behavior, thermal threshold, database, or
Flutter emergency presentation.

## Data handling

Raw audio, metadata, model binaries, archives, known-hosts details, private keys,
and physical-test logs stay local and are ignored. Reports should contain only
aggregate result/status information and redacted errors. Existing `.cursor/` is not
read or modified by this toolkit.
