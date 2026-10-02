#!/usr/bin/env python3
"""Independent raw-state and receipt verifier for LojixV5V6Migration/1."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "LojixV5V6Migration/1"
FAMILIES = ["live-set", "gc-roots", "event-log", "container-lifecycle", "deploy-job",
            "test-run", "deployment-record", "identifier-allocation", "deployment-outbox",
            "pending-transition-intent", "nexus-configuration", "quarantined-row"]
CHANGED = {"deploy-job", "nexus-configuration"}
IMMUTABLE = set(FAMILIES) - CHANGED
META_CHANGED = {"__sema_meta", "__sema_engine_catalog"}
ENGINE_RECEIPT_TABLES = {
    "__sema_headers", "__sema_engine_chain_head", "__sema_engine_commit_log",
    "__sema_engine_versioned_commit_log", "__sema_engine_versioning_policy",
}
EXPECTED_IDENTITIES = dict(zip(FAMILIES, [
    "LiveSetFamily", "GcRootsFamily", "EventLogFamily", "ContainerLifecycleFamily",
    "DeployJobFamily", "TestRunFamily", "DeploymentRecordFamily",
    "IdentifierAllocationFamily", "DeploymentOutboxFamily",
    "PendingTransitionIntentFamily", "NexusConfigurationFamily", "QuarantinedRowFamily",
]))

def fail(message):
    raise SystemExit("v5-v6 oracle: " + message)

def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {path}: {error}")

def indexed(snapshot, field):
    entries = snapshot.get(field)
    if not isinstance(entries, list): fail(f"{field} missing")
    result = {entry.get("table"): entry for entry in entries}
    if len(result) != len(entries) or None in result: fail(f"duplicate or unnamed {field} entry")
    return result

def verify_snapshot(snapshot):
    if snapshot.get("schema") != SCHEMA or snapshot.get("snapshot") != "raw-redb-v1": fail("wrong snapshot schema")
    physical = snapshot.get("physical_tables")
    if not isinstance(physical, list) or physical != sorted(physical) or len(set(physical)) != len(physical): fail("physical roster is not sorted unique")
    families = indexed(snapshot, "families")
    if set(families) != set(FAMILIES): fail("family roster differs")
    for name, entry in families.items():
        records = entry.get("records")
        if not isinstance(records, list) or entry.get("rows") != len(records): fail(f"{name} record count")
        keys = [record.get("key_hex") for record in records]
        if keys != sorted(keys) or len(keys) != len(set(keys)): fail(f"{name} raw key order")
        if entry.get("physically_absent") != (name not in physical): fail(f"{name} physical presence")
    return families, indexed(snapshot, "engine_tables"), set(physical)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def wan_router_mapping(old_routers, new_routers, context):
    if not (isinstance(old_routers, list) and isinstance(new_routers, list) and len(old_routers) == len(new_routers)):
        fail(f"{context} router topology")
    for before, after in zip(old_routers, new_routers):
        if before.get("node") != after.get("node"): fail(f"{context} router node identity")
        if before.get("router") is None:
            if after.get("router") is not None: fail(f"{context} leaf router option")
            continue
        if not isinstance(before.get("first_interface"), str): fail(f"{context} WAN interface absent")
        if before.get("second_interface") != after.get("interface"): fail(f"{context} WLAN interface was not retained")
        for key in ["wlan_band", "integer", "wlan_standard", "secret_reference_option", "backup_wireless_option", "country_code"]:
            if before.get(key) != after.get(key): fail(f"{context} router field changed {key}")

def normalize_wan_debug(rendering):
    if not isinstance(rendering, str): fail("typed rendering absent")
    normalized, changes = re.subn(r'first_interface: ".*?", second_interface: ', 'interface: ', rendering)
    if changes == 0: fail("typed WAN mapping absent")
    return normalized

def equal_after_declared_wan(old, new, context):
    if old == new:
        return
    if normalize_wan_debug(old) != new:
        fail(f"{context} changed beyond WAN mapping")

def semantic(source, destination):
    jobs = (source["deploy-job"].get("semantic", []), destination["deploy-job"].get("semantic", []))
    if not all(isinstance(rows, list) for rows in jobs) or len(jobs[0]) != len(jobs[1]): fail("typed deploy-job evidence")
    for old_job, new_job in zip(*jobs):
        wan_router_mapping(old_job.get("routers"), new_job.get("routers"), "deploy-job")
        equal_after_declared_wan(old_job.get("typed_debug"), new_job.get("typed_debug"), "deploy-job")
    configs = (source["nexus-configuration"].get("semantic"), destination["nexus-configuration"].get("semantic"))
    if not all(isinstance(rows, list) and len(rows) == 1 for rows in configs): fail("typed configuration evidence")
    old, new = configs[0][0], configs[1][0]
    for key in ["desired_key", "ordinary_socket_mode", "owner_socket_mode", "daemon_host", "meta_configure_occurred"]:
        if old.get(key) != new.get(key): fail(f"configuration changed {key}")
    for key in ["ordinary_socket_path", "owner_socket_path", "state_directory_path"]:
        if not isinstance(old.get(key), str) or not isinstance(new.get(key), str) or old[key] == new[key]: fail(f"configuration relocation {key}")
    wan_router_mapping(old.get("routers"), new.get("routers"), "configuration")
    # This complete public typed rendering guards fields outside the selected projection.
    full = old.get("typed_debug")
    for old_key, new_key in [("ordinary_socket_path", "ordinary_socket_path"), ("owner_socket_path", "owner_socket_path"), ("state_directory_path", "state_directory_path")]:
        full = full.replace(f'{old_key}: "{old[old_key]}"', f'{new_key}: "{new[new_key]}"')
    equal_after_declared_wan(full, new.get("typed_debug"), "configuration")

def receipt(false_path, true_path, stdout_path):
    false = Path(false_path).read_bytes(); committed = Path(true_path).read_bytes()
    base = json.loads(false); final = json.loads(committed)
    if base.get("schema") != SCHEMA or base.get("committed") is not False: fail("false receipt shape")
    if final.get("schema") != SCHEMA or final.get("committed") is not True: fail("committed receipt shape")
    if final.get("verified_receipt_sha256") != hashlib.sha256(false).hexdigest(): fail("committed receipt does not bind false receipt bytes")
    if Path(stdout_path).read_text().strip() != committed.decode().strip(): fail("success stdout does not equal committed receipt")
    return base, final

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True); parser.add_argument("--destination", required=True)
    parser.add_argument("--migration-json", required=True); parser.add_argument("--migration-committed-json", required=True)
    parser.add_argument("--converter-stdout", required=True)
    parser.add_argument("--source-before"); parser.add_argument("--source-after")
    parser.add_argument("--old-archive"); parser.add_argument("--new-archive")
    parser.add_argument("--destination-db")
    args = parser.parse_args()
    source = load(args.source); destination = load(args.destination)
    sf, se, source_roster = verify_snapshot(source); df, de, destination_roster = verify_snapshot(destination)
    base, final = receipt(args.migration_json, args.migration_committed_json, args.converter_stdout)
    if final.get("source_schema") != 5 or final.get("destination_schema") != 6: fail("receipt schema transition")
    if final.get("old_runtime_pin") != "3fc95f0cf4eaf14ff62898c4783ebbc670fdf96b": fail("old producer pin")
    if final.get("new_runtime_source_baseline") != "94d8b69a546560e9d3c8300c6114e8dac7df67ea": fail("new baseline")
    if final.get("converter_source_revision") != "6be34e8141f2bef26510004197d3256a762380a1": fail("converter revision")
    if args.source_before:
        if final.get("source_sha256") != sha(args.source_before): fail("receipt source database digest")
    if args.destination_db and final.get("destination_sha256") != sha(args.destination_db): fail("receipt destination database digest")
    if args.old_archive and final.get("source_archive_sha256") != sha(args.old_archive): fail("receipt old archive digest")
    if args.new_archive and final.get("destination_archive_sha256") != sha(args.new_archive): fail("receipt new archive digest")
    for name in IMMUTABLE:
        if sf[name] != df[name]: fail(f"immutable family changed: {name}")
    for name in CHANGED:
        if [r["key_hex"] for r in sf[name]["records"]] != [r["key_hex"] for r in df[name]["records"]]: fail(f"changed family key changed: {name}")
    semantic(sf, df)
    receipt_families = {item.get("family"): item for item in final.get("families", [])}
    if set(receipt_families) != set(FAMILIES) - {"quarantined-row"}: fail("receipt family roster")
    for name, item in receipt_families.items():
        if item.get("source_table_sha256") != sf[name].get("sha256") or item.get("destination_table_sha256") != df[name].get("sha256"):
            fail(f"receipt family digest {name}")
        source_records = {r["key_hex"]: r["value_sha256"] for r in sf[name]["records"]}
        destination_records = {r["key_hex"]: r["value_sha256"] for r in df[name]["records"]}
        for record in item.get("records", []):
            key = record.get("key_hex")
            if source_records.get(key) != record.get("source_sha256") or destination_records.get(key) != record.get("destination_sha256"):
                fail(f"receipt record digest {name}/{key}")
        receipt_keys = [record.get("key_hex") for record in item.get("records", [])]
        source_keys = [record["key_hex"] for record in sf[name]["records"]]
        destination_keys = [record["key_hex"] for record in df[name]["records"]]
        if receipt_keys != source_keys or receipt_keys != destination_keys or len(set(receipt_keys)) != len(receipt_keys):
            fail(f"receipt record roster {name}")
    source_meta = se.get("__sema_meta", {}).get("records")
    destination_meta = de.get("__sema_meta", {}).get("records")
    if source_meta != [{"key_hex":"736368656d615f76657273696f6e","value_sha256":hashlib.sha256((5).to_bytes(8,"little")).hexdigest(),"value_bytes":8}] or destination_meta != [{"key_hex":"736368656d615f76657273696f6e","value_sha256":hashlib.sha256((6).to_bytes(8,"little")).hexdigest(),"value_bytes":8}]:
        fail("raw metadata transition")
    counters = se.get("__sema_engine_counters", {})
    raw_counters = {entry["key"]: entry["value"] for entry in counters.get("numeric", [])}
    if raw_counters != final.get("engine_counters"):
        fail("raw engine counters")
    if counters.get("numeric_sha256") != final.get("engine_counter_digest", {}).get("sha256"):
        fail("framed engine counter digest")
    engine_records = final.get("engine_records", {})
    if set(engine_records) != ENGINE_RECEIPT_TABLES:
        fail("receipt engine history/header roster")
    for name, item in engine_records.items():
        observed = se.get(name)
        if not observed or {key: value for key, value in observed.items() if key not in {"table", "rows"}} != item:
            fail(f"receipt engine snapshot {name}")
    if final.get("engine_meta_source_digest") != {key: value for key, value in se["__sema_meta"].items() if key not in {"table", "rows"}}:
        fail("receipt source metadata digest")
    if final.get("engine_meta_destination_digest") != {key: value for key, value in de["__sema_meta"].items() if key not in {"table", "rows"}}:
        fail("receipt destination metadata digest")
    for name in set(se) | set(de):
        if name not in META_CHANGED and se.get(name) != de.get(name): fail(f"engine table changed: {name}")
    added = destination_roster - source_roster
    if added != set(final.get("added_empty_family_tables", [])): fail("receipt added physical roster")
    if not added.issubset(set(FAMILIES)): fail("unexpected added physical table")
    for name in added:
        if df[name]["rows"] != 0: fail(f"added table is nonempty: {name}")
    if set(final.get("physical_tables_source", [])) != source_roster: fail("receipt source roster")
    if set(final.get("physical_tables_destination", [])) != destination_roster: fail("receipt destination roster")
    catalog_rows = final.get("catalog", [])
    catalog = {entry.get("table"): entry for entry in catalog_rows}
    expected = {"deploy-job": (5, 15), "nexus-configuration": (12, 16)}
    if set(catalog) != set(FAMILIES) or len(catalog) != len(catalog_rows): fail("catalog identities roster")
    for name, item in catalog.items():
        before, after = item.get("source_hash"), item.get("destination_hash")
        if not (isinstance(before, list) and isinstance(after, list) and len(before) == len(after) == 32): fail(f"catalog hash shape {name}")
        if name in expected:
            old, new = expected[name]
            if before != [old] * 32 or after != [new] * 32: fail(f"catalog change {name}")
        elif before != after: fail(f"unexpected catalog change {name}")
    old_catalog_rows = se["__sema_engine_catalog"].get("identities", [])
    new_catalog_rows = de["__sema_engine_catalog"].get("identities", [])
    old_catalog = {entry["table"]: entry for entry in old_catalog_rows}
    new_catalog = {entry["table"]: entry for entry in new_catalog_rows}
    if set(old_catalog) != set(FAMILIES) or set(new_catalog) != set(FAMILIES) or len(old_catalog) != len(old_catalog_rows) or len(new_catalog) != len(new_catalog_rows): fail("raw catalog roster")
    for name in FAMILIES:
        old_entry, new_entry = old_catalog[name], new_catalog[name]
        if old_entry["family"] != EXPECTED_IDENTITIES[name] or new_entry["family"] != EXPECTED_IDENTITIES[name]: fail(f"catalog family {name}")
        old_hash, new_hash = old_entry["schema_hash_hex"], new_entry["schema_hash_hex"]
        if catalog[name]["source_hash"] != list(bytes.fromhex(old_hash)) or catalog[name]["destination_hash"] != list(bytes.fromhex(new_hash)):
            fail(f"catalog receipt/raw binding {name}")
        expected_hash = {"deploy-job": ("05", "0f"), "nexus-configuration": ("0c", "10")}.get(name)
        if expected_hash:
            if old_hash != expected_hash[0] * 32 or new_hash != expected_hash[1] * 32: fail(f"raw catalog hash {name}")
        elif old_hash != new_hash: fail(f"raw catalog changed {name}")
    if args.source_before or args.source_after:
        if not (args.source_before and args.source_after): fail("both source byte snapshots required")
        if sha(args.source_before) != sha(args.source_after): fail("source store/archive bytes changed")
    print(json.dumps({"schema": SCHEMA, "qualified": True, "source_tables": len(source_roster), "destination_tables": len(destination_roster)}, sort_keys=True))

if __name__ == "__main__": main()
