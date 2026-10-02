{
  flake,
  pkgs,
  system,
}:
let
  toolchain = flake.inputs.fenix.packages.${system}.complete.withComponents [
    "cargo"
    "rustc"
  ];
  craneLib = (flake.inputs.crane.mkLib pkgs).overrideToolchain toolchain;
  helperSource = flake.inputs.lojix-migrate-final;
  vendor = craneLib.vendorCargoDeps {
    src = helperSource;
    cargoLock = "${helperSource}/migration-v5-v6/Cargo.lock";
  };
  # The immutable target must already be realized locally.  The helpers below
  # are recreated from the original pinned schema source only because the
  # retained helper artifact is unavailable; this is not a producer build.
  converterPackage = "/nix/store/l04p8r0d38mp7nkp94b5wzk4vq9pwcr6-lojix-migrate-v5-v6-0.1.0";
  converter = builtins.appendContext "${converterPackage}/bin/lojix-migrate-v5-v6" {
    "${converterPackage}" = {
      path = true;
    };
  };
  revision = "cea66fd53a72c13f4e03ca04a67c8a4336df1ac2";
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "lojix-immutable-converter-rich-sparse-replay";
  version = revision;
  inherit helperSource;
  nativeBuildInputs = [
    toolchain
    pkgs.stdenv.cc
    pkgs.coreutils
    pkgs.python3
  ];
  dontUnpack = true;

  buildPhase = ''
    mkdir work .cargo capture
    cp -R --no-preserve=mode,ownership "$helperSource"/. work/
    chmod -R u+w work
    cp -R --no-preserve=mode,ownership ${vendor}/. .cargo/
    mkdir -p work/migration-v5-v6/src/bin
    cp ${../fixtures/qualification-driver.rs} work/migration-v5-v6/src/bin/qualification-driver.rs
    cp ${../fixtures/qualification-variants.rs} work/migration-v5-v6/src/bin/qualification-variants.rs
    cp ${../fixtures/raw-snapshot-oracle.rs} work/migration-v5-v6/src/bin/raw-snapshot-oracle.rs
    cd work
    cargo build --offline --manifest-path migration-v5-v6/Cargo.toml --bin qualification-driver --bin raw-snapshot-oracle
    helper="$PWD/migration-v5-v6/target/debug"
    test -x "$helper/qualification-driver"
    test -x "$helper/raw-snapshot-oracle"
    test -x ${converter}
    for mode in rich sparse; do
      root="$NIX_BUILD_TOP/fixture-$mode"
      capture_dir="$NIX_BUILD_TOP/capture/$mode"
      mkdir -p "$capture_dir"
      "$helper/qualification-driver" "$root" "$mode" > "$capture_dir/fixture.stdout" 2> "$capture_dir/fixture.stderr"
      cp "$root/old-state/store.db" "$capture_dir/source-before.db"
      cp "$root/old-startup.rkyv" "$capture_dir/source-before.rkyv"
      LOJIX_ORACLE_SCHEMA=old "$helper/raw-snapshot-oracle" SNAPSHOT "$root/old-state/store.db" > "$capture_dir/old-snapshot.json"
      set +e
      ${converter} "$root/old-startup.rkyv" "$root/new-startup.rkyv" "$root/destination" > "$capture_dir/converter.stdout" 2> "$capture_dir/converter.stderr"
      status=$?
      set -e
      printf '%s\n' "$status" > "$capture_dir/converter.status"
      test "$status" -eq 0
      LOJIX_ORACLE_SCHEMA=new "$helper/raw-snapshot-oracle" SNAPSHOT "$root/destination/store.db" > "$capture_dir/destination-snapshot.json"
      cp "$root/old-state/store.db" "$capture_dir/source-after.db"
      cp "$root/old-startup.rkyv" "$capture_dir/source-after.rkyv"
      cmp "$capture_dir/source-before.db" "$capture_dir/source-after.db"
      cmp "$capture_dir/source-before.rkyv" "$capture_dir/source-after.rkyv"
      ${pkgs.python3}/bin/python ${../oracle/v5_v6.py} --converter-source-revision ${revision} --source "$capture_dir/old-snapshot.json" --destination "$capture_dir/destination-snapshot.json" --migration-json "$root/destination/migration.json" --migration-committed-json "$root/destination/migration.committed.json" --converter-stdout "$capture_dir/converter.stdout" --source-before "$capture_dir/source-before.db" --source-after "$capture_dir/source-after.db" --destination-db "$root/destination/store.db" --old-archive "$capture_dir/source-before.rkyv" --new-archive "$root/new-startup.rkyv" > "$capture_dir/oracle.json"
      cp "$root/destination/migration.json" "$capture_dir/migration.json"
      cp "$root/destination/migration.committed.json" "$capture_dir/migration-committed.json"
    done
  '';

  installPhase = ''
    mkdir -p "$out"
    cp -R "$NIX_BUILD_TOP/capture"/. "$capture_dir/"
    printf '%s\n' "$helperSource" > "$capture_dir/helper-source"
    printf '%s\n' '${converter}' > "$capture_dir/converter-path"
    sha256sum ${converter} > "$capture_dir/converter-sha256"
    printf '%s\n' '${revision}' > "$capture_dir/converter-source-revision"
  '';
}
