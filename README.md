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
