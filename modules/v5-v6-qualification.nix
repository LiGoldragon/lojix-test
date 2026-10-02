{
  flake,
  pkgs,
  system,
  source,
  sourceRevision,
  expectedConverterStatus,
  expectedError,
  runMigrationCases ? false,
}:
let
  toolchain = flake.inputs.fenix.packages.${system}.complete.withComponents [
    "cargo"
    "rustc"
  ];
  craneLib = (flake.inputs.crane.mkLib pkgs).overrideToolchain toolchain;
  vendor = craneLib.vendorCargoDeps {
    src = source;
    cargoLock = "${source}/migration-v5-v6/Cargo.lock";
  };
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "lojix-v5-v6-consumer-qualification";
  version = sourceRevision;
  src = source;
  nativeBuildInputs = [
    toolchain
    pkgs.stdenv.cc
    pkgs.coreutils
    pkgs.findutils
    pkgs.gnugrep
    pkgs.python3
  ];
  dontUnpack = true;
  buildPhase = ''
    runHook preBuild
    mkdir work .cargo capture fixture
    cp -R --no-preserve=mode,ownership "$src"/. work/
    chmod -R u+w work
    cp -R --no-preserve=mode,ownership ${vendor}/. .cargo/
    mkdir -p work/migration-v5-v6/src/bin
    cp ${../fixtures/qualification-driver.rs} work/migration-v5-v6/src/bin/qualification-driver.rs
    cp ${../fixtures/qualification-variants.rs} work/migration-v5-v6/src/bin/qualification-variants.rs
    cp ${../fixtures/raw-snapshot-oracle.rs} work/migration-v5-v6/src/bin/raw-snapshot-oracle.rs
    cd work
    # Crane's dummy dependency source must receive this nested independent lock.
    cp migration-v5-v6/Cargo.lock migration-v5-v6/Cargo.lock.checked
    mv migration-v5-v6/Cargo.lock.checked migration-v5-v6/Cargo.lock
    export LOJIX_MIGRATION_SOURCE_REVISION=${sourceRevision}
    cargo build --offline --manifest-path migration-v5-v6/Cargo.toml --bin raw-snapshot-oracle
    run_capture() {
      label="$1"
      shift
      set +e
      "$@" > "$NIX_BUILD_TOP/capture/$label.stdout" 2> "$NIX_BUILD_TOP/capture/$label.stderr"
      status=$?
      set -e
      printf '%s status=%s\n' "$label" "$status" >&2
      if [ "$status" -ne 0 ]; then
        printf '%s stdout:\n' "$label" >&2
        cat "$NIX_BUILD_TOP/capture/$label.stdout" >&2 || true
        printf '%s stderr:\n' "$label" >&2
        cat "$NIX_BUILD_TOP/capture/$label.stderr" >&2 || true
        exit "$status"
      fi
    }
    run_capture fixture cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin qualification-driver -- "$NIX_BUILD_TOP/fixture"
    cp "$NIX_BUILD_TOP/fixture/old-state/store.db" "$NIX_BUILD_TOP/capture/source-before.db"
    cp "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/capture/source-before.rkyv"
    find "$NIX_BUILD_TOP/fixture/old-state" -maxdepth 1 -type f ! -name store.db -printf '%f\n' | sort > "$NIX_BUILD_TOP/capture/source-before-sidecars"
    run_capture old-snapshot env LOJIX_ORACLE_SCHEMA=old cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin raw-snapshot-oracle -- SNAPSHOT "$NIX_BUILD_TOP/fixture/old-state/store.db"
    set +e
    cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin lojix-migrate-v5-v6 -- "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/fixture/new-startup.rkyv" "$NIX_BUILD_TOP/fixture/destination" > "$NIX_BUILD_TOP/capture/converter.stdout" 2> "$NIX_BUILD_TOP/capture/converter.stderr"
    converter_status=$?
    set -e
    printf 'converter status=%s\n' "$converter_status" >&2
    printf 'converter stdout:\n' >&2
    cat "$NIX_BUILD_TOP/capture/converter.stdout" >&2
    printf 'converter stderr:\n' >&2
    cat "$NIX_BUILD_TOP/capture/converter.stderr" >&2
    test "$converter_status" -eq ${toString expectedConverterStatus}
    if [ -n '${expectedError}' ]; then
      grep -F -- "${expectedError}" "$NIX_BUILD_TOP/capture/converter.stderr"
    fi
    if [ "$converter_status" -eq 0 ]; then
      run_capture destination-snapshot env LOJIX_ORACLE_SCHEMA=new cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin raw-snapshot-oracle -- SNAPSHOT "$NIX_BUILD_TOP/fixture/destination/store.db"
      cp "$NIX_BUILD_TOP/fixture/old-state/store.db" "$NIX_BUILD_TOP/capture/source-after.db"
      cp "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/capture/source-after.rkyv"
      run_capture source-after-snapshot env LOJIX_ORACLE_SCHEMA=old cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin raw-snapshot-oracle -- SNAPSHOT "$NIX_BUILD_TOP/fixture/old-state/store.db"
      find "$NIX_BUILD_TOP/fixture/old-state" -maxdepth 1 -type f ! -name store.db -printf '%f\n' | sort > "$NIX_BUILD_TOP/capture/source-after-sidecars"
      cmp "$NIX_BUILD_TOP/capture/source-before.rkyv" "$NIX_BUILD_TOP/capture/source-after.rkyv"
      cmp "$NIX_BUILD_TOP/capture/source-before-sidecars" "$NIX_BUILD_TOP/capture/source-after-sidecars"
      printf '%s\n' 'source archive and sidecar roster unchanged' > "$NIX_BUILD_TOP/capture/source-archive-preservation.status"
      set +e
      ${pkgs.python3}/bin/python ${../oracle/v5_v6.py} --source "$NIX_BUILD_TOP/capture/old-snapshot.stdout" --destination "$NIX_BUILD_TOP/capture/destination-snapshot.stdout" --migration-json "$NIX_BUILD_TOP/fixture/destination/migration.json" --migration-committed-json "$NIX_BUILD_TOP/fixture/destination/migration.committed.json" --converter-stdout "$NIX_BUILD_TOP/capture/converter.stdout" --source-before "$NIX_BUILD_TOP/capture/source-before.db" --source-after "$NIX_BUILD_TOP/capture/source-after.db" --destination-db "$NIX_BUILD_TOP/fixture/destination/store.db" --old-archive "$NIX_BUILD_TOP/capture/source-before.rkyv" --new-archive "$NIX_BUILD_TOP/fixture/new-startup.rkyv" > "$NIX_BUILD_TOP/capture/comparator.stdout" 2> "$NIX_BUILD_TOP/capture/comparator.stderr"
      comparator_status=$?
      set -e
      printf '%s\n' "$comparator_status" > "$NIX_BUILD_TOP/capture/comparator.status"
      printf 'comparator status=%s\n' "$comparator_status" >&2
      if [ "$comparator_status" -ne 0 ]; then
        cat "$NIX_BUILD_TOP/capture/comparator.stdout" >&2 || true
        cat "$NIX_BUILD_TOP/capture/comparator.stderr" >&2 || true
        exit "$comparator_status"
      fi
      cp "$NIX_BUILD_TOP/fixture/destination/migration.json" "$NIX_BUILD_TOP/capture/migration.json"
      cp "$NIX_BUILD_TOP/fixture/destination/migration.committed.json" "$NIX_BUILD_TOP/capture/migration.committed.json"
      ${
        if runMigrationCases then
          ''
            ${pkgs.python3}/bin/python ${../fixtures/migration-cases.py} \
              --converter "$PWD/migration-v5-v6/target/debug/lojix-migrate-v5-v6" \
              --driver "$PWD/migration-v5-v6/target/debug/qualification-driver" \
              --raw-oracle "$PWD/migration-v5-v6/target/debug/raw-snapshot-oracle" \
              --oracle ${../oracle/v5_v6.py} \
              --output "$NIX_BUILD_TOP/capture/migration-cases"
          ''
        else
          ""
      }
    fi
    printf '%s\n' "$converter_status" > "$NIX_BUILD_TOP/capture/converter.status"
    run_capture rollback cargo run --offline --manifest-path migration-v5-v6/Cargo.toml --bin qualification-driver -- "$NIX_BUILD_TOP/fixture" verify-old
    runHook postBuild
  '';
  installPhase = ''
    mkdir -p "$out"
    cp -R "$NIX_BUILD_TOP/capture"/. "$out/"
    cp "$PWD/migration-v5-v6/target/debug/qualification-driver" "$out/qualification-driver"
    cp "$PWD/migration-v5-v6/target/debug/raw-snapshot-oracle" "$out/raw-snapshot-oracle"
    printf '%s\n' '${sourceRevision}' > "$out/converter-source-revision"
    printf '%s\n' 'converter trial completed; raw source snapshot and old Store rollback clone recorded' > "$out/status"
  '';
}
