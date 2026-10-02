#!/usr/bin/env python3
"""Synthetic interruption and refusal trials for the immutable v5-to-v6 CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import sys


FAULTS = (
    "after-stage", "before-publish", "after-publish", "before-commit-receipt",
    "commit-receipt-written", "before-success",
)

FSYNC_PROBE_MAX = 32


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest(root):
    return (sha(root / "old-state/store.db"), sha(root / "old-startup.rkyv"))


def tree_inventory(path):
    if not path.exists():
        return []
    return sorted(str(item.relative_to(path)) for item in path.rglob("*"))


def receipt_state(root):
    destination = root / "destination"
    false = destination / "migration.json"
    committed = destination / "migration.committed.json"
    result = {"destination_tree": tree_inventory(destination), "migration_json": false.exists(), "committed_json": committed.exists()}
    if false.exists():
        try: result["migration_json_committed"] = json.loads(false.read_text()).get("committed")
        except json.JSONDecodeError: result["migration_json_committed"] = "invalid"
    if committed.exists():
        try: result["committed_json_committed"] = json.loads(committed.read_text()).get("committed")
        except json.JSONDecodeError: result["committed_json_committed"] = "invalid"
    return result


def accepted(root, status, stdout):
    false = root / "destination/migration.json"
    committed = root / "destination/migration.committed.json"
    if status != 0 or not false.exists() or not committed.exists():
        return False
    try:
        false_bytes = false.read_bytes()
        final = json.loads(committed.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (final.get("schema") == "LojixV5V6Migration/1" and final.get("committed") is True
            and final.get("verified_receipt_sha256") == hashlib.sha256(false_bytes).hexdigest()
            and stdout.strip() == committed.read_text().strip())


def prepare(driver, case_root, mode="rich"):
    completed = subprocess.run([str(driver), str(case_root), mode], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise AssertionError(f"fixture setup failed: {completed.stderr}")


def invoke(converter, root, environment=None, pause=None, allow_unobserved=False, on_barrier=None, resume=False):
    env = os.environ.copy()
    env.update(environment or {})
    command = [str(converter), str(root / "old-startup.rkyv"), str(root / "new-startup.rkyv"), str(root / "destination")]
    if not pause:
        completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
        return completed.returncode, completed.stdout, completed.stderr
    process = subprocess.Popen(command, env={**env, "LOJIX_MIGRATION_PAUSE_AT": pause}, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = []
    while True:
        ready, _, _ = select.select([process.stderr], [], [], 30)
        if not ready:
            if allow_unobserved:
                stdout, tail = process.communicate()
                stderr.append(tail)
                return process.returncode, stdout, "".join(stderr)
            process.kill(); raise AssertionError(f"{pause}: missing qualification barrier")
        line = process.stderr.readline()
        if not line:
            if allow_unobserved:
                stdout, tail = process.communicate()
                stderr.append(tail)
                return process.returncode, stdout, "".join(stderr)
            process.kill(); raise AssertionError(f"{pause}: process ended before qualification barrier")
        stderr.append(line)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("qualification_barrier") == pause:
            if on_barrier is not None:
                on_barrier(root)
            if resume:
                process.stdin.write("x")
                process.stdin.flush()
                try:
                    stdout, tail = process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, tail = process.communicate()
                    raise AssertionError(f"{pause}: did not resume after barrier")
                stderr.append(tail)
                return process.returncode, stdout, "".join(stderr)
            process.kill()
            break
    stdout, tail = process.communicate()
    stderr.append(tail)
    return process.returncode, stdout, "".join(stderr)


def assert_refusal(name, root, before, result):
    status, stdout, stderr = result
    after = source_digest(root)
    state = receipt_state(root)
    if status == 0:
        raise AssertionError(f"{name}: expected nonzero result")
    if accepted(root, status, stdout):
        raise AssertionError(f"{name}: accepted result")
    # A kill after `commit-receipt-written` can leave a syntactically true file.
    # It is evidence of an interrupted publication, never an accepted target:
    # acceptance also requires the converter's successful exit and matching stdout.
    if after != before:
        raise AssertionError(f"{name}: source changed")
    return {"case": name, "status": status, "stdout": stdout, "stderr": stderr, "accepted": False, "source_before_sha256": before, "source_after_sha256": after, **state}


def assert_success(name, root, before, result):
    status, stdout, stderr = result
    if not accepted(root, status, stdout):
        raise AssertionError(f"{name}: expected accepted migration")
    after = source_digest(root)
    if after != before:
        raise AssertionError(f"{name}: source changed")
    return {"case": name, "status": status, "stdout": stdout, "stderr": stderr, "accepted": True, "source_before_sha256": before, "source_after_sha256": after, **receipt_state(root)}


def fault_case(converter, driver, work, label):
    root = work / f"pause-{label}"
    prepare(driver, root)
    before = source_digest(root)
    result = invoke(converter, root, pause=label)
    if result[0] != -signal.SIGKILL or f'"qualification_barrier":"{label}"' not in result[2].replace(" ", ""):
        raise AssertionError(f"pause-{label}: expected exact barrier and SIGKILL")
    return assert_refusal(f"pause-{label}", root, before, result)


def fail_case(converter, driver, work, label, setup=None, prefix=""):
    root = work / f"fail-{prefix}{label}"
    prepare(driver, root)
    if setup is not None:
        setup(root)
    before = source_digest(root)
    return assert_refusal(f"fail-{prefix}{label}", root, before, invoke(converter, root, {"LOJIX_MIGRATION_FAIL_AT": label}))


def known_backup(root):
    sidecar = root / "old-state/store.db.schema-pre-v3.backup"
    sidecar.write_bytes((root / "old-state/store.db").read_bytes())
    sidecar.chmod(0o600)
    return sidecar


def fsync_cases(converter, driver, work, setup=None, prefix=""):

    cases = []
    for index in range(1, FSYNC_PROBE_MAX + 1):
        for edge in ("before", "after"):
            label = f"fsync-{index}-{edge}"
            root = work / f"pause-{prefix}{label}"
            prepare(driver, root)
            if setup is not None:
                setup(root)
            before = source_digest(root)
            result = invoke(converter, root, pause=label, allow_unobserved=True)
            # A non-existent barrier ends normally or at a different guard. It is evidence,
            # but is deliberately not counted as an actual fsync interruption case.
            observed = f'"qualification_barrier":"{label}"' in result[2].replace(" ", "")
            case = assert_refusal(f"pause-{prefix}{label}", root, before, result) if observed else {
                "case": f"probe-{prefix}{label}", "observed": False, "status": result[0], "stdout": result[1], "stderr": result[2],
                "accepted": accepted(root, result[0], result[1]), "source_before_sha256": before, "source_after_sha256": source_digest(root), **receipt_state(root)}
            case["observed"] = observed
            case["layout"] = prefix or "base"
            cases.append(case)
            if observed:
                cases.append(fail_case(converter, driver, work, label, setup, prefix))
    return cases


def dest_exists(converter, driver, work):
    root = work / "destination-exists"
    prepare(driver, root)
    (root / "destination").mkdir()
    before = source_digest(root)
    return assert_refusal("destination-exists", root, before, invoke(converter, root))


def archive_symlink(converter, driver, work):
    root = work / "archive-symlink"
    prepare(driver, root)
    archive = root / "old-startup.rkyv"
    target = root / "old-startup.target"
    archive.rename(target)
    archive.symlink_to(target.name)
    before = source_digest(root)
    return assert_refusal("archive-symlink", root, before, invoke(converter, root))


def archive_overlap(converter, driver, work):
    root = work / "archive-overlap"
    prepare(driver, root)
    new_archive = root / "new-startup.rkyv"
    new_archive.unlink()
    os.link(root / "old-startup.rkyv", new_archive)
    before = source_digest(root)
    return assert_refusal("archive-overlap", root, before, invoke(converter, root))


def sidecar_positive(converter, driver, work):
    root = work / "sidecar-positive"
    prepare(driver, root)
    # The immutable converter admits exactly this opaque pre-v3 backup name.
    # Its bytes are a synthetic preservation witness, not a historical producer row.
    sidecar = known_backup(root)
    before = source_digest(root)
    result = assert_success("sidecar-positive", root, before, invoke(converter, root))
    copied = root / "destination/rollback/store.db.schema-pre-v3.backup"
    if copied.read_bytes() != sidecar.read_bytes() or stat.S_IMODE(copied.stat().st_mode) != 0o600:
        raise AssertionError("sidecar-positive: copied bytes or mode")
    result["sidecar_copy"] = {"bytes": sha(copied), "mode": stat.S_IMODE(copied.stat().st_mode)}
    return result


def declared_sidecar_alias(converter, driver, work):
    root = work / "declared-sidecar-alias"
    prepare(driver, root)
    os.link(root / "old-state/store.db", root / "old-state/store.db.schema-pre-v3.backup")
    before = source_digest(root)
    return assert_refusal("declared-sidecar-alias", root, before, invoke(converter, root))


def external_hardlink_positive(converter, driver, work):
    root = work / "external-hardlink-positive"
    prepare(driver, root)
    os.link(root / "old-state/store.db", root / "unrelated-store-hardlink")
    before = source_digest(root)
    return assert_success("external-hardlink-positive", root, before, invoke(converter, root))


def sidecar_case(converter, driver, work, name, refused):
    root = work / f"sidecar-{name}"
    prepare(driver, root)
    (root / "old-state" / name).write_bytes(b"unrecognised sidecar")
    before = source_digest(root)
    if refused:
        return assert_refusal(f"sidecar-{name}", root, before, invoke(converter, root))
    result = assert_success(f"sidecar-{name}-ignored", root, before, invoke(converter, root))
    if (root / "destination/rollback" / name).exists():
        raise AssertionError(f"sidecar-{name}: unknown sidecar copied")
    result["unknown_sidecar_ignored"] = name
    return result


def interrupted_mutation(converter, driver, work, target):
    root = work / f"mutation-{target}"
    prepare(driver, root)
    if target == "backup":
        path = known_backup(root)
    elif target == "source":
        path = root / "old-state/store.db"
    else:
        path = root / "old-startup.rkyv"
    before = source_digest(root)
    before_target = sha(path)

    def mutate(_):
        with path.open("ab") as handle:
            handle.write(b"external-interruption-witness\n")
            handle.flush()
            os.fsync(handle.fileno())

    result = invoke(converter, root, pause="before-publish", on_barrier=mutate)
    if result[0] != -signal.SIGKILL:
        raise AssertionError(f"mutation-{target}: expected SIGKILL")
    after = source_digest(root)
    if target == "source":
        if after[0] == before[0] or after[1] != before[1]:
            raise AssertionError("mutation-source: external delta was not isolated")
    elif target == "archive":
        if after[1] == before[1] or after[0] != before[0]:
            raise AssertionError("mutation-archive: external delta was not isolated")
    else:
        if after != before or sha(path) == before_target:
            raise AssertionError("mutation-backup: external delta was not isolated")
    return {"case": f"mutation-{target}", "status": result[0], "stdout": result[1], "stderr": result[2],
            "accepted": False, "external_mutation": {"path": str(path.relative_to(root)), "before_sha256": before_target, "after_sha256": sha(path)},
            "source_before_sha256": before, "source_after_sha256": after, **receipt_state(root)}


def parent_replacement(converter, driver, work):
    root = work / "parent-replacement"
    prepare(driver, root)
    source = root / "old-state"
    original = root / "old-state-original"
    identity = (source.stat().st_dev, source.stat().st_ino)
    before = source_digest(root)

    def replace(_):
        os.replace(source, original)
        source.mkdir()
        (source / "replacement-marker").write_text("external replacement\n")

    result = invoke(converter, root, pause="before-success", on_barrier=replace)
    if result[0] != -signal.SIGKILL or (original.stat().st_dev, original.stat().st_ino) != identity:
        raise AssertionError("parent-replacement: original source identity was not retained")
    if (source.stat().st_dev, source.stat().st_ino) == identity:
        raise AssertionError("parent-replacement: replacement retained original identity")
    return {"case": "parent-replacement", "status": result[0], "stdout": result[1], "stderr": result[2], "accepted": False,
            "moved_source_identity": identity, "replacement_identity": (source.stat().st_dev, source.stat().st_ino),
            "moved_source_sha256": (sha(original / "store.db"), sha(root / "old-startup.rkyv")), "source_before_sha256": before, **receipt_state(root)}


def destination_replacement(converter, driver, work):
    root = work / "destination-replacement"
    prepare(driver, root)
    destination = root / "destination"
    before = source_digest(root)

    def replace(_):
        staged = root / "external-destination"
        staged.mkdir()
        (staged / "replacement-marker").write_text("external replacement\n")
        if destination.exists():
            os.replace(destination, root / "converter-destination")
        os.replace(staged, destination)

    result = invoke(converter, root, pause="before-publish", on_barrier=replace)
    if result[0] != -signal.SIGKILL or source_digest(root) != before:
        raise AssertionError("destination-replacement: source or interruption result")
    if not (destination / "replacement-marker").exists():
        raise AssertionError("destination-replacement: external destination was lost")
    return {"case": "destination-replacement", "status": result[0], "stdout": result[1], "stderr": result[2], "accepted": False,
            "source_before_sha256": before, "source_after_sha256": source_digest(root), **receipt_state(root)}


def positive_variant(converter, driver, raw_oracle, oracle, work, mode):
    root = work / f"positive-{mode}"
    prepare(driver, root, mode)
    before = source_digest(root)
    source_before = root / "source-before.db"
    shutil.copyfile(root / "old-state/store.db", source_before)
    result = assert_success(f"positive-{mode}", root, before, invoke(converter, root))
    old_snapshot, new_snapshot = root / "old.json", root / "new.json"
    for schema, database, snapshot in (("old", root / "old-state/store.db", old_snapshot), ("new", root / "destination/store.db", new_snapshot)):
        completed = subprocess.run([str(raw_oracle), "SNAPSHOT", str(database)], env={**os.environ, "LOJIX_ORACLE_SCHEMA": schema}, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise AssertionError(f"positive-{mode}: {schema} snapshot failed: {completed.stderr}")
        snapshot.write_text(completed.stdout)
    stdout = root / "converter.stdout"
    stdout.write_text(result["stdout"])
    completed = subprocess.run([sys.executable, str(oracle), "--source", str(old_snapshot), "--destination", str(new_snapshot), "--migration-json", str(root / "destination/migration.json"), "--migration-committed-json", str(root / "destination/migration.committed.json"), "--converter-stdout", str(stdout), "--source-before", str(source_before), "--source-after", str(root / "old-state/store.db"), "--destination-db", str(root / "destination/store.db"), "--old-archive", str(root / "old-startup.rkyv"), "--new-archive", str(root / "new-startup.rkyv")], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise AssertionError(f"positive-{mode}: independent oracle failed: {completed.stderr}")
    result["independent_oracle"] = json.loads(completed.stdout)
    return result


def assert_resumed_refusal(name, root, before, result, expected):
    status, stdout, stderr = result
    if status != 2 or stdout != "" or accepted(root, status, stdout):
        raise AssertionError(f"{name}: expected CLI refusal exit 2 with empty stdout")
    if expected not in stderr.lower():
        raise AssertionError(f"{name}: missing guard reason {expected}: {stderr}")
    return {"case": name, "status": status, "stdout": stdout, "stderr": stderr,
            "accepted": False, "guard_reason": expected,
            "source_before_sha256": before, "source_after_sha256": source_digest(root), **receipt_state(root)}

def resumed_input_mutation(converter, driver, work, target):
    root = work / f"resume-mutation-{target}"
    prepare(driver, root)
    path = known_backup(root) if target == "backup" else root / ("old-state/store.db" if target == "source" else "old-startup.rkyv")
    before = source_digest(root)
    original = path.read_bytes()
    witness = b"external-resumed-guard-witness\n"
    expected_after = original + witness
    def mutate(_):
        with path.open("ab") as handle:
            handle.write(witness)
            handle.flush(); os.fsync(handle.fileno())
    result = invoke(converter, root, pause="after-stage", on_barrier=mutate, resume=True)
    reason = "sidecar changed during migration" if target == "backup" else "source tuple changed during migration"
    case = assert_resumed_refusal(f"resume-mutation-{target}", root, before, result, reason)
    if path.read_bytes() != expected_after:
        raise AssertionError(f"resume-mutation-{target}: converter altered external mutation")
    after = source_digest(root)
    if target == "source" and after[1] != before[1]: raise AssertionError("resume mutation archive changed")
    if target == "archive" and after[0] != before[0]: raise AssertionError("resume mutation source changed")
    if target == "backup" and after != before: raise AssertionError("resume backup changed primary inputs")
    case["external_mutation"] = {"path": str(path.relative_to(root)), "before_sha256": hashlib.sha256(original).hexdigest(), "after_sha256": hashlib.sha256(expected_after).hexdigest()}
    return case

def resumed_root_replacement(converter, driver, work, label):
    root = work / f"resume-root-replacement-{label}"
    prepare(driver, root)
    moved = work / f"resume-root-replacement-{label}-original"
    before = source_digest(root)
    identities = {name: (path.stat().st_dev, path.stat().st_ino) for name, path in (("store", root / "old-state/store.db"), ("archive", root / "old-startup.rkyv"))}
    def replace(current):
        os.replace(current, moved)
        current.mkdir()
        (current / "replacement-marker").write_text("external root replacement\n")
    result = invoke(converter, root, pause=label, on_barrier=replace, resume=True)
    # The process was given the old spelling; its final validation must reject the replacement.
    text = result[1] + result[2]
    if result[0] != 2 or result[1] != "" or "publication directory was replaced" not in text:
        raise AssertionError(f"resume-root-replacement: expected publication replacement guard: {result[2]}")
    if {name: (path.stat().st_dev, path.stat().st_ino) for name, path in (("store", moved / "old-state/store.db"), ("archive", moved / "old-startup.rkyv"))} != identities:
        raise AssertionError("resume-root-replacement: moved source identity")
    moved_sha = (sha(moved / "old-state/store.db"), sha(moved / "old-startup.rkyv"))
    if moved_sha != before:
        raise AssertionError("resume root replacement: moved input bytes changed")
    return {"case": f"resume-root-replacement-{label}", "status": result[0], "stdout": result[1], "stderr": result[2], "accepted": False,
            "guard_reason": "publication directory was replaced", "moved_source_identity": identities,
            "source_before_sha256": before, "moved_source_sha256": moved_sha}


def resumed_destination_replacement(converter, driver, work, label):
    root = work / f"resume-destination-{label}"
    prepare(driver, root)
    destination = root / "destination"
    before = source_digest(root)
    def replace(_):
        external = root / "external-destination"
        external.mkdir()
        (external / "replacement-marker").write_text("external destination replacement\n")
        if destination.exists(): os.replace(destination, root / "converter-destination")
        os.replace(external, destination)
    result = invoke(converter, root, pause=label, on_barrier=replace, resume=True)
    expected = "file exists (os error 17)" if label == "before-publish" else "publication directory was replaced"
    case = assert_resumed_refusal(f"resume-destination-{label}", root, before, result, expected)
    if not (destination / "replacement-marker").exists():
        raise AssertionError(f"resume-destination-{label}: external destination lost")
    if source_digest(root) != before: raise AssertionError(f"resume-destination-{label}: source changed")
    return case


def active_variant_refusal(converter, driver, work, mode):
    root = work / f"refusal-{mode}"
    prepare(driver, root, mode)
    before = source_digest(root)
    expected = {"active-test": "live test run holds migration", "active-container": "live container lifecycle holds migration", "active-deployment": "unacknowledged outbox holds migration", "active-intent": "pending intent holds migration"}[mode]
    return assert_resumed_refusal(f"refusal-{mode}", root, before, invoke(converter, root), expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--raw-oracle", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(dir=args.output, prefix="cases-") as temporary:
        work = Path(temporary)
        for label in FAULTS:
            cases.append(fault_case(args.converter, args.driver, work, label))
            cases.append(fail_case(args.converter, args.driver, work, label))
        cases.extend(fsync_cases(args.converter, args.driver, work))
        cases.extend(fsync_cases(args.converter, args.driver, work, known_backup, "backup-"))
        cases.append(dest_exists(args.converter, args.driver, work))
        cases.append(archive_symlink(args.converter, args.driver, work))
        cases.append(archive_overlap(args.converter, args.driver, work))
        cases.append(sidecar_positive(args.converter, args.driver, work))
        cases.append(declared_sidecar_alias(args.converter, args.driver, work))
        cases.append(sidecar_case(args.converter, args.driver, work, "store.db.schema-pre-v3.backup.pending", True))
        cases.append(sidecar_case(args.converter, args.driver, work, "store.db.schema-unknown", True))
        cases.append(sidecar_case(args.converter, args.driver, work, "store.db.unknown", False))
        cases.append(external_hardlink_positive(args.converter, args.driver, work))
        for target in ("source", "archive", "backup"):
            cases.append(interrupted_mutation(args.converter, args.driver, work, target))
        cases.append(parent_replacement(args.converter, args.driver, work))
        cases.append(destination_replacement(args.converter, args.driver, work))
        for target in ("source", "archive", "backup"):
            cases.append(resumed_input_mutation(args.converter, args.driver, work, target))
        for label in ("before-publish", "before-success"):
            cases.append(resumed_root_replacement(args.converter, args.driver, work, label))
        for label in ("before-publish", "before-success"):
            cases.append(resumed_destination_replacement(args.converter, args.driver, work, label))
        cases.append(positive_variant(args.converter, args.driver, args.raw_oracle, args.oracle, work, "sparse"))
        cases.append(positive_variant(args.converter, args.driver, args.raw_oracle, args.oracle, work, "no-router"))
        cases.append(positive_variant(args.converter, args.driver, args.raw_oracle, args.oracle, work, "history"))
        for mode in ("active-test", "active-container", "active-deployment", "active-intent"):
            cases.append(active_variant_refusal(args.converter, args.driver, work, mode))
    (args.output / "migration-cases.json").write_text(json.dumps({"schema": "LojixV5V6Migration/1", "cases": cases}, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
