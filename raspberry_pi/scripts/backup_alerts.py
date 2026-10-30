#!/usr/bin/env python3
"""Consistent SQLite backup, including committed WAL contents; no overwrite."""
import argparse
import os
import stat
from contextlib import closing
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if not args.source.is_file() or args.destination.exists():
        parser.error("Source must exist and destination must be new")
    if os.name == 'posix':
        parent = args.destination.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            parser.error('Backup directory must be owned by the current user with owner-only permissions (0700)')
    # Explicit creation mode defeats a permissive umask. O_EXCL also rejects
    # pre-existing symlinks. Windows deployments must restrict directory ACLs.
    fd = os.open(args.destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if os.name == 'posix':
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    with closing(sqlite3.connect(args.source.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(args.destination)) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    print(f"Backup verified: {args.destination}")


if __name__ == "__main__":
    main()
