"""Run each broker's importer when its CSV files change.

    python run_imports.py           import whatever changed since last time, then stop
    python run_imports.py --watch   keep running and import as soon as files arrive
    python run_imports.py --force   re-import every broker, changed or not

A broker counts as changed when a CSV in its folder is added, edited or
removed, or when its importer's code (or importers/common.py) changes, so a
bug fix is picked up without new exports. Each successful import records both
fingerprints in the import_runs table, so deleting the database re-imports
everything.
"""

import argparse
import hashlib
import time
from datetime import datetime
from pathlib import Path

import duckdb

import importers.common
from importers import ibkr, lightyear, trading212
from importers.common import print_account_summary
from init_db import DATABASE_FILE, apply_sql_files

# broker name -> (importer module, folders holding its CSV files)
SOURCES = {
    "trading212": (trading212, [trading212.csv_folder]),
    "lightyear": (lightyear, [lightyear.csv_folder]),
    "ibkr": (ibkr, [ibkr.csv_folder / "trades", ibkr.csv_folder / "cash"]),
}

POLL_SECONDS = 2


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def csv_files(folders):
    return sorted(path for folder in folders if folder.is_dir() for path in folder.glob("*.csv"))


def hash_files(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(f"{path.parent.name}/{path.name}\n".encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def fingerprint(folders):
    """A hash of every CSV's name and contents, or None if there are no CSVs."""
    files = csv_files(folders)
    return hash_files(files) if files else None


def code_files(module):
    """The importer's own file plus the shared helpers it uses."""
    files = [Path(importers.common.__file__)]
    if getattr(module, "__file__", None):
        files.insert(0, Path(module.__file__))
    return files


def code_fingerprint(module):
    return hash_files(code_files(module))


def last_fingerprints(connection, broker):
    """(files fingerprint, code fingerprint) from the last import, or None."""
    return connection.execute(
        "SELECT files_fingerprint, code_fingerprint FROM import_runs WHERE broker = ?",
        [broker],
    ).fetchone()


def import_reason(current, last, force):
    """Why this broker needs importing, or None if it doesn't."""
    if force:
        return "forced"
    if last is None:
        return "first import"

    changed = [
        label
        for label, now, before in zip(("files", "importer code"), current, last)
        if now != before
    ]
    return " and ".join(changed) + " changed" if changed else None


def record_import(connection, broker, fingerprints, count):
    connection.execute(
        """
        INSERT OR REPLACE INTO import_runs (
            broker, files_fingerprint, code_fingerprint, transaction_count, imported_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [broker, *fingerprints, count, datetime.now()],
    )


def import_changed(sources=SOURCES, database_file=DATABASE_FILE, force=False):
    """Run the importer of every broker whose files changed.

    Returns {broker: transaction count} for the brokers that were imported.
    """
    imported = {}
    with duckdb.connect(str(database_file)) as connection:
        apply_sql_files(connection)

        for broker, (module, folders) in sources.items():
            files = fingerprint(folders)
            if files is None:
                log(f"{broker}: no CSV files, skipped (existing data kept)")
                continue

            current = (files, code_fingerprint(module))
            reason = import_reason(current, last_fingerprints(connection, broker), force)
            if reason is None:
                continue

            log(f"{broker}: {reason}, importing...")
            try:
                count = module.run(connection)
            except Exception as error:
                # Not recorded, so the next run tries this broker again.
                log(f"{broker}: import FAILED: {error}")
                continue

            record_import(connection, broker, current, count)
            imported[broker] = count
            log(f"{broker}: saved {count} transactions")
            print_account_summary(connection, module.ACCOUNT["account_id"])

    if not imported:
        log("Nothing new to import")
    return imported


def folder_state(folders):
    """File names, sizes and modification times: cheap to check every poll."""
    state = []
    for path in csv_files(folders):
        try:
            stat = path.stat()
        except FileNotFoundError:  # removed between listing and stat
            continue
        state.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(state)


def watch(sources=SOURCES, database_file=DATABASE_FILE, poll_seconds=POLL_SECONDS):
    import_changed(sources, database_file)

    seen = {broker: folder_state(folders) for broker, (_, folders) in sources.items()}
    pending = set()
    log(f"Watching {len(sources)} brokers for new CSV files. Press Ctrl+C to stop.")

    while True:
        time.sleep(poll_seconds)

        ready = []
        for broker, (_, folders) in sources.items():
            state = folder_state(folders)
            if state != seen[broker]:
                # Still changing (e.g. a copy in progress): wait for it to settle.
                seen[broker] = state
                pending.add(broker)
            elif broker in pending:
                pending.discard(broker)
                ready.append(broker)

        if ready:
            try:
                import_changed({broker: sources[broker] for broker in ready}, database_file)
            except duckdb.IOException as error:
                # Usually the database is open in another program; try again shortly.
                log(f"Database busy, will retry: {error}")
                pending.update(ready)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", action="store_true", help="keep running and import new files")
    parser.add_argument("--force", action="store_true", help="re-import every broker")
    args = parser.parse_args()

    if args.watch:
        try:
            watch()
        except KeyboardInterrupt:
            log("Stopped watching")
    else:
        import_changed(force=args.force)


if __name__ == "__main__":
    main()
