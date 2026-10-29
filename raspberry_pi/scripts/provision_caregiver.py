#!/usr/bin/env python3
"""Local administrator provisioning; never exposes the secret to backend logs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True)
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    if len(args.installation) != 32 or any(c not in "0123456789abcdef" for c in args.installation):
        parser.error("Copy the 32-character installation ID from the Caregiver pairing dialog")
    records = json.loads(args.file.read_text()) if args.file.exists() else {}
    if args.installation in records:
        parser.error("Installation already provisioned; explicitly remove its verifier to revoke before reprovisioning")
    secret = secrets.token_urlsafe(32)
    records[args.installation] = hashlib.sha256(secret.encode()).hexdigest()
    args.file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.file.with_name(args.file.name + ".new")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
        json.dump(records, target)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, args.file)
    print("Enter this pairing secret on this installation only:")
    print(secret)


if __name__ == "__main__":
    main()
