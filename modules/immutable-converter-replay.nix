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
      out="$NIX_BUILD_TOP/capture/$mode"
      mkdir -p "$out"
      "$helper/qualification-driver" "$root" "$mode" > "$out/fixture.stdout" 2> "$out/fixture.stderr"
      cp "$root/old-state/store.db" "$out/source-before.db"
      cp "$root/old-startup.rkyv" "$out/source-before.rkyv"
      LOJIX_ORACLE_SCHEMA=old "$helper/raw-snapshot-oracle" SNAPSHOT "$root/old-state/store.db" > "$out/old-snapshot.json"
      set +e
      ${converter} "$root/old-startup.rkyv" "$root/new-startup.rkyv" "$root/destination" > "$out/converter.stdout" 2> "$out/converter.stderr"
      status=$?
      set -e
      printf '%s\n' "$status" > "$out/converter.status"
      test "$status" -eq 0
      LOJIX_ORACLE_SCHEMA=new "$helper/raw-snapshot-oracle" SNAPSHOT "$root/destination/store.db" > "$out/destination-snapshot.json"
      cp "$root/old-state/store.db" "$out/source-after.db"
      cp "$root/old-startup.rkyv" "$out/source-after.rkyv"
      cmp "$out/source-before.db" "$out/source-after.db"
      cmp "$out/source-before.rkyv" "$out/source-after.rkyv"
      ${pkgs.python3}/bin/python ${../oracle/v5_v6.py} --converter-source-revision ${revision} --source "$out/old-snapshot.json" --destination "$out/destination-snapshot.json" --migration-json "$root/destination/migration.json" --migration-committed-json "$root/destination/migration.committed.json" --converter-stdout "$out/converter.stdout" --source-before "$out/source-before.db" --source-after "$out/source-after.db" --destination-db "$root/destination/store.db" --old-archive "$out/source-before.rkyv" --new-archive "$root/new-startup.rkyv" > "$out/oracle.json"
      cp "$root/destination/migration.json" "$out/migration.json"
      cp "$root/destination/migration.committed.json" "$out/migration-committed.json"
    done
  '';

  installPhase = ''
    mkdir -p "$out"
    cp -R "$NIX_BUILD_TOP/capture"/. "$out/"
    printf '%s\n' "$helperSource" > "$out/helper-source"
    printf '%s\n' '${converter}' > "$out/converter-path"
    sha256sum ${converter} > "$out/converter-sha256"
    printf '%s\n' '${revision}' > "$out/converter-source-revision"
  '';
}
