#!/usr/bin/env python3
"""Consistent SQLite backup, including committed WAL contents; no overwrite."""
import argparse
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
    # Reserve the destination without overwriting an existing backup.
    with args.destination.open("xb"):
        pass
    with closing(sqlite3.connect(args.source.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(args.destination)) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    print(f"Backup verified: {args.destination}")


if __name__ == "__main__":
    main()
