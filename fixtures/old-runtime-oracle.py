#!/usr/bin/env python3
"""Independent terminal-only old Nexus rollback witness verifier."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def families(snapshot):
    values = snapshot.get("families")
    if not isinstance(values, list):
        raise SystemExit("old runtime oracle: family snapshot missing")
    result = {value.get("table"): value for value in values}
    if len(result) != len(values) or None in result:
        raise SystemExit("old runtime oracle: invalid family roster")
    return result


def engine(snapshot):
    values = snapshot.get("engine_tables")
    result = {value.get("table"): value for value in values}
    if len(result) != len(values) or None in result:
        raise SystemExit("old runtime oracle: invalid engine roster")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--startup", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    before_snapshot, after_snapshot = load(args.before), load(args.after)
    before, after = families(before_snapshot), families(after_snapshot)
    before_engine, after_engine = engine(before_snapshot), engine(after_snapshot)
    evidence = load(args.startup)
    if evidence.get("error") is not None:
        raise SystemExit("old runtime oracle: startup script reported failure")
    initial, final = evidence.get("before", {}), evidence.get("after", {})
    if initial.get("archive") != final.get("archive") or initial.get("source_store") != final.get("source_store"):
        raise SystemExit("old runtime oracle: source archive or source store changed")
    if initial.get("db") == final.get("db"):
        raise SystemExit("old runtime oracle: startup did not persist its expected XDG state")
    if set(before) != set(after):
        raise SystemExit("old runtime oracle: family roster changed")
    for table in before:
        if table != "deploy-job" and before[table] != after[table]:
            raise SystemExit(f"old runtime oracle: unexpected family change: {table}")
    prior, later = before["deploy-job"], after["deploy-job"]
    if prior.get("rows") != 1 or later.get("rows") != 0:
        raise SystemExit("old runtime oracle: terminal deployment cursor was not retracted exactly")
    fixed = {"__sema_engine_catalog", "__sema_meta", "__sema_headers", "__sema_engine_versioning_policy"}
    for table in fixed:
        if before_engine.get(table) != after_engine.get(table):
            raise SystemExit(f"old runtime oracle: fixed engine table changed: {table}")
    for table in ("__sema_engine_commit_log", "__sema_engine_versioned_commit_log"):
        old, new = before_engine[table], after_engine[table]
        old_rows = {row["key_hex"]: row for row in old["records"]}
        new_rows = {row["key_hex"]: row for row in new["records"]}
        if len(new_rows) != len(old_rows) + 1 or any(new_rows.get(key) != row for key, row in old_rows.items()):
            raise SystemExit(f"old runtime oracle: {table} continuity")
    old_chain, new_chain = before_engine["__sema_engine_chain_head"], after_engine["__sema_engine_chain_head"]
    if [row["key_hex"] for row in old_chain["records"]] != [row["key_hex"] for row in new_chain["records"]]:
        raise SystemExit("old runtime oracle: chain head key roster")
    old_counters = {row["key"]: row["value"] for row in before_engine["__sema_engine_counters"]["numeric"]}
    new_counters = {row["key"]: row["value"] for row in after_engine["__sema_engine_counters"]["numeric"]}
    expected_counters = {"commit_log_count": 35, "latest_commit_sequence": 35, "latest_snapshot": 35, "versioned_log_count": 35, "engine_storage_layout": 7}
    if old_counters != {**expected_counters, "commit_log_count": 34, "latest_commit_sequence": 34, "latest_snapshot": 34, "versioned_log_count": 34} or new_counters != expected_counters:
        raise SystemExit("old runtime oracle: counter progression")
    Path(args.output).write_text(json.dumps({
        "schema": "LojixOldRuntimeRollback/1",
        "qualified": True,
        "source_archive_preserved": True,
        "source_store_preserved": True,
        "terminal_deploy_cursor": "retracted",
        "xdg_store_changed": True,
    }, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
