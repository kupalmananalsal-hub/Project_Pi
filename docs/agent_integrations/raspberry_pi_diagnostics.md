# Raspberry Pi 5 diagnostic boundaries

The preflight helper has four safety levels:

| Level | Scope | Permission |
| --- | --- | --- |
| 0 | Source review, fixtures and command plan | Default |
| 1 | Named read-only host probes | Explicit connection approval |
| 2 | Audio capture or sensor test | Separate explicit test approval |
| 3 | Configuration, driver, service or threshold change | Reviewed change approval |
| 4 | Deployment or production operation | Deployment authorization |

Level 1 is limited to OS/kernel/Python, CPU temperature, memory/storage, systemd
state, ALSA enumeration, device-node names, declared boot overlays, expected model
filenames, and a loopback backend status request. It does not open a microphone,
read I2C pixels, modify GPIO, restart a service, install a driver, or upload logs.

API authentication is optional and off by default (no-token mode). The probe
neither reads nor sends a token: it records only the HTTP status code of
`/api/status`. `401` is classified as `BACKEND_REACHABLE_AUTH_REQUIRED`
(listening, auth enforced; application health still unverified), `200` as
`BACKEND_REACHABLE_AUTH_NOT_ENFORCED` (no-token mode, or a pre-Milestone-1
backend), and no response as `BACKEND_UNREACHABLE`. With auth enabled,
authenticated health checks need the root-only token and are a separate,
authorized step.

Raspberry Pi 5 GPIO is behind RP1, so any GPIO library/driver choice must be
validated on the deployed OS and hardware rather than inferred from older Pi
guides. Project_Pi already uses `gpiozero`/`lgpio` in the backend and systemd
configuration; this toolkit deliberately does not replace that behavior. See the
[Raspberry Pi documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).

For the ReSpeaker 2-Mics Pi HAT V2, the vendor FAQ identifies its codec as
TLV320AIC3104 at I2C address `0x18`. That fact applies only after the actual board
revision is verified. The older `respeaker/mic_hat` repository is GPL-2.0 and is
kept as reference only; it is neither copied nor installed. See Seeed's
[V2 FAQ](https://wiki.seeedstudio.com/respeaker_2_mics_pi_hat_faq/).

The MLX90640 workflow validates offline 24x32 frame fixtures. A physical sensor
read is Level 2 and must also confirm wiring, bus/address, frame rate, calibration,
and service ownership. It must never be conflated with fixture validation.
