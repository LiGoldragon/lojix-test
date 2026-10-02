{ pkgs, ... }:
let
  helper = builtins.storePath "/nix/store/p5gbyz9fxphlxs9xgx1di39h9cxaq1ka-lojix-v5-v6-consumer-qualification-6be34e8141f2bef26510004197d3256a762380a1";
  converterPackage = builtins.storePath "/nix/store/l04p8r0d38mp7nkp94b5wzk4vq9pwcr6-lojix-migrate-v5-v6-0.1.0";
  converter = "${converterPackage}/bin/lojix-migrate-v5-v6";
  revision = "cea66fd53a72c13f4e03ca04a67c8a4336df1ac2";
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "lojix-immutable-converter-rich-sparse-replay";
  version = revision;
  nativeBuildInputs = [
    pkgs.coreutils
    pkgs.python3
  ];
  dontUnpack = true;

  buildPhase = ''
    test -x ${helper}/qualification-driver
    test -x ${helper}/raw-snapshot-oracle
    test -x ${converter}
    mkdir capture
    for mode in rich sparse; do
      root="$NIX_BUILD_TOP/fixture-$mode"
      out="$NIX_BUILD_TOP/capture/$mode"
      mkdir -p "$out"
      ${helper}/qualification-driver "$root" "$mode" > "$out/fixture.stdout" 2> "$out/fixture.stderr"
      cp "$root/old-state/store.db" "$out/source-before.db"
      cp "$root/old-startup.rkyv" "$out/source-before.rkyv"
      LOJIX_ORACLE_SCHEMA=old ${helper}/raw-snapshot-oracle SNAPSHOT "$root/old-state/store.db" > "$out/old-snapshot.json"
      set +e
      ${converter} "$root/old-startup.rkyv" "$root/new-startup.rkyv" "$root/destination" > "$out/converter.stdout" 2> "$out/converter.stderr"
      status=$?
      set -e
      printf '%s\n' "$status" > "$out/converter.status"
      test "$status" -eq 0
      LOJIX_ORACLE_SCHEMA=new ${helper}/raw-snapshot-oracle SNAPSHOT "$root/destination/store.db" > "$out/destination-snapshot.json"
      cp "$root/old-state/store.db" "$out/source-after.db"
      cp "$root/old-startup.rkyv" "$out/source-after.rkyv"
      cmp "$out/source-before.db" "$out/source-after.db"
      cmp "$out/source-before.rkyv" "$out/source-after.rkyv"
      ${pkgs.python3}/bin/python ${../oracle/v5_v6.py} --converter-source-revision ${revision} --source "$out/old-snapshot.json" --destination "$out/destination-snapshot.json" --migration-json "$root/destination/migration.json" --migration-committed-json "$root/destination/migration.committed.json" --converter-stdout "$out/converter.stdout" --source-before "$out/source-before.db" --source-after "$out/source-after.db" --destination-db "$root/destination/store.db" --old-archive "$out/source-before.rkyv" --new-archive "$root/new-startup.rkyv" > "$out/oracle.json"
      cp "$root/destination/migration.json" "$out/migration.json"
      cp "$root/destination/migration-committed.json" "$out/migration-committed.json"
    done
  '';

  installPhase = ''
    mkdir -p "$out"
    cp -R "$NIX_BUILD_TOP/capture"/. "$out/"
    printf '%s\n' '${helper}' > "$out/helper-path"
    printf '%s\n' '${converter}' > "$out/converter-path"
    sha256sum ${converter} > "$out/converter-sha256"
    printf '%s\n' '${revision}' > "$out/converter-source-revision"
  '';
}
