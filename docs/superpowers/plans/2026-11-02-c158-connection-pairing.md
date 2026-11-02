# C1.58 IP/port-only pairing implementation

Base 74acc81, branch codex/c158-connection-pairing, isolated Windows development checkout.

1. Private bounded SQLite registry and local-only approval CLI; minimal public discovery, expiring request/proof. No remote approval endpoint.
2. Scoped caregiver/Resident authentication with existing durable replay/ACK identity preserved. Existing backend/KWS administrator tokens remain compatible. Paired Residents cannot mute.
3. Flutter secure credential storage by stable Pi identity, server challenge proof before using saved credentials at an edited address, persistent enrollment request and operator code. Remove manual credentials from both settings screens; editable IP and port only.
4. Focused registry/ASGI/Flutter pairing, settings, retry and delivery checks; no full suites. Build both existing flavors/signers; export reviewed source and deployment instructions without push, merge or device access.
