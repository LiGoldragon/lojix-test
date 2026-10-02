# lojix-test

This repository holds a hermetic Nix replay of one public Lojix behavioral
boundary. It contains no Lojix production source and drives pinned public
source inputs instead.

`checks/horizon-layout-refusal.nix` retains two build outputs:

- `red` runs exactly `cargo test --offline --test schema_one_migration
  horizon_layout_change_refuses_v5_open_and_destructive_reset` against the
  immutable test-only prefix. It passes only when that one test runs and fails
  at the open-refusal assertion.
- `green` runs the same command against the immutable converged source and
  passes only when that one test passes.

The fixture synthetically stamps schema version 5. Its red evidence is a
**HEADER REFUSAL** witness, not an old-schema row migration. The red trial
aborts at the open-refusal assertion, so it does not reach the reset or
byte-preservation checks; the green trial does.

The check stores command, exit status, stdout, and stderr under each output.
Run the repository checks through Nix; builds use configured remote builders.

`checks/v5-v6-converter-qualification.nix` separately qualifies the pinned
`6be34e` copy-only converter. It creates a disposable public v5 store,
captures source and destination raw-redb snapshots, validates the committed
receipt against raw framed table and engine digests, receipt record rosters,
catalog identities, and retained input bytes. The rich fixture includes a
terminal deployment and Nexus configuration carrying a WAN/WLAN Horizon
definition; the independent oracle permits only the declared WAN removal and
three configuration-path relocations.

Its retained interruption matrix records six named publication barriers and
injected failures, then discovers fsync barriers independently for both the
ordinary and accepted exact-backup layouts. Unmatched fsync labels are recorded
as probes and do not count as fault coverage. Each case retains status, stdout,
stderr, source hashes, destination-tree inventory, and false/committed receipt
state.  A true receipt
left by a killed process is not an accepted migration: acceptance requires a
zero exit, exact stdout, and the committed receipt binding the false receipt's
SHA-256 bytes.

The check also builds the independently pinned `3fc95f` `lojix-nexus` binary
offline and starts it only against the disposable terminal fixture. It waits
for the exact readiness record, validates both socket paths are confined to
the fixture, then sends `SIGTERM`; it makes no client connections. The capture
keeps the old binary, startup output and status, raw snapshots before and after
startup, and archive/source hashes. Startup is required to preserve the source store and archive. The copied XDG
store must preserve the captured catalog, metadata, headers, policy, and every
prior commit/versioned-log row while adding exactly the source-backed terminal
retraction progress.

The present matrix includes rich, sparse configuration-only, no-router, and
allocator-backed 300-history positive migrations with independent raw and
semantic oracle runs. It exercises active test/container/deployment refusal
fixtures, separate public terminal-pending-intent and bound-outbox refusals,
declared/unknown/pending sidecar refusals, an ignored unrelated sibling witness,
accepted unrelated source hardlinks, exact known-backup preservation, both backup-layout fsync discovery,
and deliberate source/archive/backup mutation and parent/destination replacement
races at real barriers. The interruption cases remain kill diagnostics; the
separate resumed cases require the converter's source-tuple, sidecar, publication
identity, and destination-existence guards to reject. External mutations are
recorded as such and are not misreported as converter writes. Full live cutover, materializer projections,
and live tuple recovery remain external gates.
