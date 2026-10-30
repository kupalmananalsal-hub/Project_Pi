"""Version 2 durable alert protocol; independent of sensors and ML."""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

from alert_trace import trace_alert


def authenticate(installation, token):
    # Provision SHA-256 verifiers out of band; no shared development fallback.
    path = os.getenv("PROJECT_PI_CAREGIVER_CREDENTIALS")
    if not path or not isinstance(installation, str) or not isinstance(token, str):
        return False
    with open(path, encoding="utf-8") as source:
        credentials = json.load(source)
    expected = credentials.get(installation)
    return isinstance(expected, str) and hmac.compare_digest(
        expected, hashlib.sha256(token.encode()).hexdigest())


def decode_control(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 16384:
        raise ValueError("message_size")
    message = json.loads(raw)
    if not isinstance(message, dict) or message.get("protocol_version") != 2:
        raise ValueError("protocol_version")
    return message


def replay_eligible(event, delivery, now=None):
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(event["persisted_at"])).total_seconds()
    return (event.get("decision_state") == "critical" and 0 <= age <= 300
            and not delivery.get("user_confirmed_at"))


class DeliverySessions:
    def __init__(self, heartbeat_interval=15, heartbeat_timeout=10, clock=None):
        self.active = {}
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def serve(self, ws, store):
        await ws.accept()
        installation = None
        tasks = []
        send_lock = asyncio.Lock()

        async def send(kind, **fields):
            async with send_lock:
                await asyncio.wait_for(ws.send_json(dict(protocol_version=2, type=kind, **fields)), 5)

        try:
            hello = decode_control(await asyncio.wait_for(ws.receive_text(), 10))
            installation = hello.get("installation_id")
            if hello.get("type") != "authenticate" or not authenticate(installation, hello.get("token")):
                await ws.close(code=1008, reason="authentication_failed")
                return
            # Reject concurrent same-identity connections rather than displacing an active phone.
            if installation in self.active:
                await ws.close(code=1008, reason="installation_already_connected")
                return
            self.active[installation] = ws
            instance, high = await asyncio.to_thread(store.delivery_boundary)
            recovery_cursor = await asyncio.to_thread(store.recovery_cursor, installation, high, self.clock())
            await send("connected", instance=instance, high_water=high, recovery_cursor=recovery_cursor)
            heartbeat = {"nonce": None, "event": asyncio.Event()}
            replay_lock = asyncio.Lock()
            state = {"cursor": None, "ready": False}

            async def deliver(after, mode):
                async with replay_lock:
                    current_instance, current_high = await asyncio.to_thread(store.delivery_boundary)
                    boundary = high if mode == "replay" else current_high
                    if current_instance != instance or after > boundary or boundary > current_high:
                        raise ValueError("recovery_boundary_changed")
                    events = await asyncio.to_thread(store.replay, after, boundary)
                    cursor = after
                    for event in events:
                        identity = event.get("event_id")
                        if not identity:
                            cursor = event["sequence"]
                            continue
                        delivery = await asyncio.to_thread(store.offer, installation, identity)
                        present = (not delivery.get("presented_at") and not delivery.get("user_confirmed_at"))
                        if mode == "replay":
                            present = replay_eligible(event, delivery, self.clock())
                        await send("alert", event_id=identity, sequence=event["sequence"],
                                   persisted_at=event["persisted_at"], delivery_mode=mode,
                                   present=present, event=event)
                        trace_alert("websocket_send", identity, "succeeded", caregiver_id=installation, delivery_mode=mode)
                        cursor = event["sequence"]
                    more = len(events) == 100 and cursor < boundary
                    if not more:
                        cursor = boundary
                    state["cursor"] = cursor
                    state["ready"] = not more
                    await send("replay_complete", cursor=cursor, high_water=boundary, more=more, instance=instance)

            async def receive():
                while True:
                    message = decode_control(await ws.receive_text())
                    kind = message.get("type")
                    if kind == "heartbeat_ack":
                        if message.get("nonce") != heartbeat["nonce"]:
                            raise ValueError("heartbeat_nonce")
                        heartbeat["event"].set()
                    elif kind == "replay_request":
                        cursor = message.get("cursor")
                        if type(cursor) is not int or cursor < 0 or message.get("instance") != instance:
                            raise ValueError("invalid_replay_cursor")
                        await deliver(cursor, "replay")
                    elif kind in ("ack_received", "ack_presented", "ack_user_confirmed"):
                        identity, sequence = message.get("event_id"), message.get("sequence")
                        if not isinstance(identity, str) or len(identity) > 128 or type(sequence) is not int or sequence <= 0:
                            raise ValueError("invalid_ack")
                        if "installation_id" in message or "caregiver_id" in message:
                            raise ValueError("identity_spoof")
                        try:
                            await asyncio.to_thread(store.acknowledge, installation, identity, sequence, kind)
                        except ValueError as error:
                            trace_alert(kind, identity, "failed", reason=str(error))
                            raise
                        await send("ack_committed", event_id=identity, sequence=sequence, acknowledgement=kind)
                        trace_alert(kind, identity, "persisted", caregiver_id=installation)
                    else:
                        raise ValueError("unknown_message_type")

            async def live():
                # SQLite is the delivery source, not the lossy in-memory publication queue.
                # Polling also covers commit-before-publication crashes and queue overflow.
                while True:
                    await asyncio.sleep(0.25)
                    cursor = state["cursor"]
                    if cursor is not None and state["ready"]:
                        _, latest = await asyncio.to_thread(store.delivery_boundary)
                        if latest > cursor:
                            await deliver(cursor, "live")

            async def pulse():
                while True:
                    await asyncio.sleep(self.heartbeat_interval)
                    heartbeat["nonce"] = secrets.token_hex(16)
                    heartbeat["event"].clear()
                    await send("heartbeat", nonce=heartbeat["nonce"])
                    await asyncio.wait_for(heartbeat["event"].wait(), self.heartbeat_timeout)

            tasks = [asyncio.create_task(f()) for f in (receive, live, pulse)]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            pass
        except Exception as error:
            trace_alert("delivery_session", None, "failed", reason=str(error) if isinstance(error, ValueError) else type(error).__name__)
            try:
                await asyncio.wait_for(ws.close(code=1008, reason="invalid_or_interrupted_session"), 2)
            except Exception:
                pass
        finally:
            if installation and self.active.get(installation) is ws:
                del self.active[installation]
            for task in tasks:
                task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass
